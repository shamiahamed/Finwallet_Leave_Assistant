
import logging
import re
from dataclasses import dataclass
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool

from app.api.deps import (
    get_balance_service,
    get_department_service,
    get_employee_service,
    get_leave_request_service,
    get_policy_service,
)
from app.core.config import get_settings
from app.exceptions.errors import (
    AppError,
    EmployeeNotFoundError,
    InvalidFilterError,
)
from app.llm.dispatcher import dispatch_query
from app.llm.intent_parser import GroqParseError, parse_intent
from app.llm.response_formatter import (
    format_group_leave_history,
    format_response,
)
from app.schemas.chat import ChatRequest, ChatResponse, LLMMetrics
from app.schemas.intent import QueryIntent
from app.services.balance_service import BalanceService
from app.services.conversation_service import (
    ConversationContext,
    ConversationService,
    normalize_employee_id,
)
from app.services.department_service import DepartmentService
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService
from app.services.policy_service import PolicyService
from app.utils.dates import asks_submission_date, detect_leave_date_range
from app.utils.document_names import extract_document_mentions
from app.utils.scope_resolver import (
    asks_currently_on_leave,
    asks_unstructured_policy_detail,
    detect_balance_scope,
    detect_balance_threshold,
    detect_department_name,
    detect_document_name,
    detect_known_employee_name,
    detect_leave_type,
    detect_document_reference,
    detect_unsupported_leave_type,
    detect_unresolved_employee_reference,
    is_balance_count_question,
    is_department_breakdown_question,
    is_document_comparison_request,
    is_document_follow_up,
    is_group_leave_history_question,
    is_headcount_question,
    is_leave_history_question,
)
from app.utils.sse import stream_answer

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Chat"])

_MAX_QUESTION_LENGTH = 1000

_POLICY_DETAIL_UNAVAILABLE = (
    "The Leave Policy worksheet contains only annual days, accrual, and "
    "payment, so it does not include that detail. Upload a relevant policy "
    "document to answer this question."
)

_SUBMISSION_DATE_UNAVAILABLE = (
    "The Leave Requests worksheet does not store a submission or application "
    "date. It only contains each request's start date, end date, days, and "
    "status. I can filter by the leave-date range instead."
)

_HISTORY_EMPLOYEE_REQUIRED = (
    "I can check leave history, but I need to know which employee. "
    "Please provide an employee ID or full name."
)

_GREETING_RESPONSE = (
    "Hi! I'm Finwallet, your Employee Leave Management Assistant. "
    "How may I help you today? You can ask me about leave balances, leave "
    "requests, leave policies, employees, departments, or uploaded leave "
    "policy documents."
)

_GREETING_RE = re.compile(
    r"(?:(?:hi|hello|hey)(?:\s+there)?|"
    r"good\s+(?:morning|afternoon|evening))"
    r"(?:\s*,?\s*finwallet)?"
    r"\s*[!.?,]*",
    re.IGNORECASE,
)

_CAPABILITIES_RESPONSE = (
    "I can help with:\n"
    "  - Employee lookups, employee lists, and headcounts by department or status.\n"
    "  - Leave balances, including balances by employee, department, or leave type.\n"
    "  - Leave requests and leave history, filtered by employee, department, "
    "status, leave type, or date range.\n"
    "  - Leave policies and department-level leave summaries.\n"
    "  - Questions about uploaded policy documents.\n\n"
    "Try: \"Show employees in Finance\", \"What is EMP001's leave balance?\", "
    "\"Show pending leave requests\", or \"What is the Sick Leave policy?\""
)

_CAPABILITIES_RE = re.compile(
    r"(?:please\s+)?(?:"
    r"what\s+can\s+(?:you|finwallet)\s+do(?:\s+for\s+me)?|"
    r"what\s+do\s+you\s+do|"
    r"what\s+can\s+you\s+help\s+(?:me\s+)?with|"
    r"what\s+are\s+your\s+(?:capabilities|skills)|"
    r"how\s+can\s+you\s+help(?:\s+me)?|"
    r"what\s+(?:questions|things)\s+can\s+i\s+ask(?:\s+you)?|"
    r"what\s+(?:can|may)\s+i\s+ask(?:\s+you)?|"
    r"help(?:\s+me)?|"
    r"show\s+(?:me\s+)?examples?"
    r")[\s?.!]*",
    re.IGNORECASE,
)

# Detect questions asking for the difference between leave balance and
# leave history, so we can answer with a targeted concept explanation
# instead of the generic capabilities list.
_BALANCE_VS_HISTORY_RE = re.compile(
    r"\b(?:difference|distinction|vs\.?|versus|compare)\b[^?]{0,80}\b(?:leave\s+)?balances?\b[^?]{0,80}\b(?:leave\s+)?history\b|"
    r"\b(?:leave\s+)?history\b[^?]{0,80}\b(?:difference|distinction|vs\.?|versus|compare)\b[^?]{0,80}\b(?:leave\s+)?balances?\b",
    re.IGNORECASE,
)

_BALANCE_VS_HISTORY_RESPONSE = (
    "Leave balance and leave history are different things:\n"
    "  - Leave balance is your entitlement: how many days you are allowed "
    "to take, how many you have used, and how many remain.\n"
    "  - Leave history is your record of leave requests: each request you "
    "have submitted, its dates, leave type, and approval status.\n\n"
    "Ask me about your balance (e.g. \"What is EMP001's leave balance?\") "
    "or your history (e.g. \"Show leave history for EMP001\")."
)


_EMPLOYEE_LIST_RE = re.compile(
    r"\b(?:list|show|display|find|get|view|see|give\s+me)\b"
    r"[^?]{0,60}\b(?:employees|staff)\b",
    re.IGNORECASE,
)

_EMPLOYEE_LIST_EXCLUDE_RE = re.compile(
    r"\b(?:leave|leaves|request|requests|balance|balances|policy|policies|"
    r"history|taken|used|took|headcount|how\s+many|count)\b",
    re.IGNORECASE,
)

# Detect "Compare X balances by department" style questions that should route
# to department balance aggregation rather than employee-level balance listing.
_DEPT_BALANCE_COMPARE_RE = re.compile(
    r"\bcompar\w*\b[^?]{0,80}\b(?:sick|casual|earned|unpaid|maternity|paternity|"
    r"leave)\s+balances?\b[^?]{0,40}\bby\s+departments?\b",
    re.IGNORECASE,
)

# Extract a candidate department name from employee-list questions such as
# "Show employees in Finance" or "Show employees in a department that does not exist".
_DEPARTMENT_CANDIDATE_RE = re.compile(
    r"\b(?:in|for|of|within|from)\s+([A-Z][A-Za-z]+(?:\s+[A-Z][A-Za-z]+)*)",
    re.IGNORECASE,
)

# Detect whether a date-range question asks about start dates, end dates, or
# the default overlap semantics.
_START_DATE_RE = re.compile(r"\bstarting\s+in\b", re.IGNORECASE)
_END_DATE_RE = re.compile(r"\bending\s+in\b", re.IGNORECASE)

conversation_service = ConversationService()


def _is_greeting(question: str) -> bool:
    return bool(_GREETING_RE.fullmatch(question.strip()))


def _is_capabilities_question(question: str) -> bool:
    return bool(_CAPABILITIES_RE.fullmatch(question.strip()))


def _is_employee_list_question(question: str) -> bool:
    text = question.strip()
    return bool(_EMPLOYEE_LIST_RE.search(text)) and not bool(
        _EMPLOYEE_LIST_EXCLUDE_RE.search(text)
    )


def _detect_employment_status(question: str) -> str | None:
    lowered = question.lower()
    if re.search(r"\binactive\b", lowered):
        return "Inactive"
    if re.search(r"\bactive\b", lowered):
        return "Active"
    return None


@dataclass
class _PreparedAnswer:
    conversation_id: str
    context: ConversationContext
    intent: QueryIntent
    metrics: dict | None
    result: Any
    answer: str
    data: dict | list | None
    evidence: dict | None
    question: str = ""
    resolved_pending: bool = False
    pending_to_set: bool = False
    compared: bool = False


def _validate_question(raw: str) -> str:
    question = raw.strip()

    if not question:
        raise HTTPException(
            status_code=422,
            detail="Question cannot be empty.",
        )

    if len(question) > _MAX_QUESTION_LENGTH:
        raise HTTPException(
            status_code=422,
            detail=(
                f"Question is too long "
                f"(max {_MAX_QUESTION_LENGTH} characters)."
            ),
        )

    return question


def _department_names(employees: EmployeeService) -> list[str]:
    return (
        employees._repo.employees["Department"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )


def _leave_type_names(employees: EmployeeService) -> list[str]:
    return (
        employees._repo.leave_policy["Leave Type"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )


def _employee_names(employees: EmployeeService) -> list[str]:
    return (
        employees._repo.employees["Full Name"]
        .dropna()
        .astype(str)
        .unique()
        .tolist()
    )


def _deterministic_intent(
    question: str,
    employees: EmployeeService,
) -> QueryIntent | None:
    """Return a confident intent without calling the LLM, or None.

    Only clear, high-confidence cases are resolved here so the LLM is not
    relied on for routing that can be decided deterministically. Anything
    ambiguous returns None and falls through to the intent parser.
    """
    department_names = _department_names(employees)

    if _is_employee_list_question(question):
        department = detect_department_name(question, department_names)
        if department is None:
            # Try to extract a candidate department name so the dispatcher
            # can validate it against the workbook instead of returning all
            # employees when the user asked for a specific non-existent dept.
            candidate_match = _DEPARTMENT_CANDIDATE_RE.search(question)
            if candidate_match:
                candidate = candidate_match.group(1).strip()
                if candidate not in department_names:
                    department = candidate
        if department is None and re.search(r"\bdepartment\b", question, re.IGNORECASE):
            raise InvalidFilterError(
                "I couldn't find that department. Please check the department name."
            )
        return QueryIntent(
            intent="employee_list",
            scope="single",
            department=department,
            employment_status=_detect_employment_status(question),
        )

    if is_headcount_question(question):
        department = detect_department_name(question, department_names)

        return QueryIntent(
            intent="employee_headcount",
            scope="single",
            department=department,
            employment_status=_detect_employment_status(question),
        )

    if is_group_leave_history_question(question) or asks_currently_on_leave(question):
        try:
            rng = detect_leave_date_range(question)
        except InvalidFilterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        date_mode = "overlap"
        if _START_DATE_RE.search(question):
            date_mode = "start_date"
        elif _END_DATE_RE.search(question):
            date_mode = "end_date"
        currently = asks_currently_on_leave(question)
        # "Currently on leave" has no date range in the question, so default to
        # today's date to filter only leave that overlaps the current date.
        if currently and not rng:
            from datetime import date

            today = date.today()
            rng = (today, today)
        department = detect_department_name(question, department_names)
        return QueryIntent(
            intent="leave_requests",
            scope="all",
            department=department,
            leave_type=detect_leave_type(
                question,
                _leave_type_names(employees),
            ),
            approval_status="Approved" if currently else None,
            start_date=rng[0] if rng else None,
            end_date=rng[1] if rng else None,
            date_mode=date_mode,
            currently_on_leave=currently,
        )

    detected_scope = detect_balance_scope(
        question,
        department_names=department_names,
        leave_types=_leave_type_names(employees),
    )

    if detected_scope is None:
        return None

    return QueryIntent(
        intent="leave_balance",
        scope=detected_scope["scope"],
        employee_id=detected_scope.get("employee_id"),
        department=detected_scope.get("department"),
        leave_type=detected_scope.get("leave_type"),
    )


def _apply_deterministic_routing(
    question: str,
    intent: QueryIntent,
    employees: EmployeeService,
) -> QueryIntent:
    """Correct clear scope and headcount classifications."""
    department_names = _department_names(employees)

    if _is_employee_list_question(question):
        department = detect_department_name(question, department_names)
        return intent.model_copy(
            update={
                "intent": "employee_list",
                "scope": "single",
                "department": department or intent.department,
                "employment_status": (
                    _detect_employment_status(question)
                    or intent.employment_status
                ),
                "employee_id": None,
                "employee_name": None,
                "leave_type": None,
                "approval_status": None,
                "start_date": None,
                "end_date": None,
            }
        )

    if is_headcount_question(question):
        department = detect_department_name(
            question,
            department_names,
        )

        return intent.model_copy(
            update={
                "intent": "employee_headcount",
                "scope": "single",
                "employee_id": None,
                "employee_name": None,
                "department": department or intent.department,
                "employment_status": (
                    _detect_employment_status(question)
                    or intent.employment_status
                ),
                "leave_type": None,
                "approval_status": None,
                "start_date": None,
                "end_date": None,
            }
        )

    if is_group_leave_history_question(question) or asks_currently_on_leave(question):
        try:
            rng = detect_leave_date_range(question)
        except InvalidFilterError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        date_mode = "overlap"
        if _START_DATE_RE.search(question):
            date_mode = "start_date"
        elif _END_DATE_RE.search(question):
            date_mode = "end_date"
        currently = asks_currently_on_leave(question)
        if currently and not rng:
            from datetime import date

            today = date.today()
            rng = (today, today)
        department = detect_department_name(question, department_names)
        return intent.model_copy(
            update={
                "intent": "leave_requests",
                "scope": "all",
                "employee_id": None,
                "employee_name": None,
                "department": department or intent.department,
                "leave_type": detect_leave_type(
                    question,
                    _leave_type_names(employees),
                )
                or intent.leave_type,
                "approval_status": "Approved" if currently else None,
                "start_date": rng[0] if rng else intent.start_date,
                "end_date": rng[1] if rng else intent.end_date,
                "date_mode": date_mode,
                "currently_on_leave": currently or intent.currently_on_leave,
            }
        )

    # Department balance comparison: "Compare Sick Leave balances by department"
    if (
        intent.intent in {"leave_balance", "department_summary"}
        and _DEPT_BALANCE_COMPARE_RE.search(question)
    ):
        leave_type = (
            detect_leave_type(question, _leave_type_names(employees))
            or intent.leave_type
        )
        return intent.model_copy(
            update={
                "intent": "department_balance_summary",
                "scope": "all",
                "leave_type": leave_type,
                "department": None,
                "employee_id": None,
                "employee_name": None,
                "approval_status": None,
                "start_date": None,
                "end_date": None,
                "date_mode": "overlap",
            }
        )

    detected_scope = detect_balance_scope(
        question,
        department_names=department_names,
        leave_types=_leave_type_names(employees),
    )

    if detected_scope is None:
        return intent

    updates = {
        "intent": "leave_balance",
        "scope": detected_scope["scope"],
        "employee_id": detected_scope.get("employee_id"),
        "employee_name": None,
        "department": detected_scope.get("department"),
        "leave_type": detected_scope.get("leave_type") or intent.leave_type,
        "approval_status": None,
        "start_date": None,
        "end_date": None,
    }

    return intent.model_copy(update=updates)


def _prepare_answer(
    question: str,
    conversation_id: str | None,
    employees: EmployeeService,
    requests: LeaveRequestService,
    balances: BalanceService,
    policies: PolicyService,
    departments: DepartmentService,
    documents: Any | None,
    settings: Any,
    limit: int | None = None,
) -> _PreparedAnswer:
    question = _validate_question(question)

    resolved_id = conversation_id or str(uuid4())
    context = conversation_service.get_or_create(resolved_id)

    # Avoid duplicating the user message on an unanswered retry.
    last_message = context.history[-1] if context.history else None

    if not (
        last_message
        and last_message["role"] == "user"
        and last_message["content"] == question
    ):
        conversation_service.add_message(
            context,
            "user",
            question,
        )

    if _is_greeting(question):
        logger.info("Responded to greeting without LLM or data lookup.")
        return _PreparedAnswer(
            conversation_id=resolved_id,
            context=context,
            intent=QueryIntent(intent="greeting"),
            metrics=None,
            result={"message": _GREETING_RESPONSE},
            answer=_GREETING_RESPONSE,
            data=None,
            evidence=None,
            question=question,
        )

    if _is_capabilities_question(question):
        logger.info("Responded to capabilities question without LLM.")
        return _PreparedAnswer(
            conversation_id=resolved_id,
            context=context,
            intent=QueryIntent(intent="help"),
            metrics=None,
            result={"message": _CAPABILITIES_RESPONSE},
            answer=_CAPABILITIES_RESPONSE,
            data=None,
            evidence=None,
            question=question,
        )

    if _BALANCE_VS_HISTORY_RE.search(question):
        logger.info("Responded to balance-vs-history explanation question.")
        return _PreparedAnswer(
            conversation_id=resolved_id,
            context=context,
            intent=QueryIntent(intent="help"),
            metrics=None,
            result={"message": _BALANCE_VS_HISTORY_RESPONSE},
            answer=_BALANCE_VS_HISTORY_RESPONSE,
            data=None,
            evidence=None,
            question=question,
        )

    # Validate date expressions before the LLM can turn an invalid calendar
    # date into a generic schema error.
    try:
        detect_leave_date_range(question)
    except InvalidFilterError as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    resolved_pending = False
    unavailable_policy_detail = False
    submission_date_unavailable = False
    history_needs_employee = False
    group_history = False
    unresolved_employee: str | None = None
    targeted_clarification: str | None = None
    compared = False
    comparison_names: list[str] | None = None
    threshold_handled = False

    standalone_employee_id = normalize_employee_id(question)

    try:
        # Resolve an ID-only reply before calling the LLM.
        pending = conversation_service.resolve_pending_employee_id(
            context,
            question,
        )

        if pending and pending.get("intent") in {"leave_balance", "leave_requests"}:
            employee_id = pending.get("employee_id")

            if not employee_id:
                raise HTTPException(
                    status_code=422,
                    detail="Please provide a valid employee ID.",
                )

            # Validate the ID. If it fails, provide a safe fallback while keeping clarification pending.
            try:
                employees.get_employee(employee_id)
                valid_id = True
            except EmployeeNotFoundError:
                valid_id = False

            if valid_id:
                intent = QueryIntent(
                    intent=pending["intent"],
                    scope="single",
                    employee_id=employee_id,
                    employee_name=None,
                    leave_type=pending.get("leave_type"),
                    department=pending.get("department"),
                    approval_status=pending.get("approval_status"),
                    start_date=None,
                    end_date=None,
                    employment_status=None,
                )

                metrics = None
                resolved_pending = True

                logger.info(
                    "Resolved pending clarification: intent=%s | employee_id=%s",
                    pending["intent"],
                    employee_id,
                )
            else:
                intent = QueryIntent(intent="clarify", scope="single")
                metrics = None
                resolved_pending = False
                unresolved_employee = employee_id

        else:
            if standalone_employee_id and not context.pending_intent:
                intent = QueryIntent(intent="employee_lookup", scope="single", employee_id=standalone_employee_id)
                metrics = None
            elif detect_document_reference(question):
                intent = QueryIntent(
                    intent="document_question",
                    scope="single",
                    document_name=detect_document_name(question),
                )
                metrics = None

            else:
                # Resolve clear, high-confidence cases without calling the LLM.
                lowered_q = question.lower()
                if re.search(r"\b(show\s+more|next\s+\d+|next\s+page|more\s+results|load\s+more)\b", lowered_q):
                    if context.last_intent == "leave_requests" and context.last_request_filters:
                        filters = context.last_request_filters
                        intent = QueryIntent(
                            intent="leave_requests",
                            scope="all",
                            employee_id=filters.get("employee_id"),
                            employee_name=filters.get("employee_name"),
                            leave_type=filters.get("leave_type"),
                            approval_status=filters.get("approval_status"),
                            department=filters.get("department"),
                            start_date=filters.get("start_date"),
                            end_date=filters.get("end_date"),
                            date_mode=filters.get("date_mode") or "overlap",
                            currently_on_leave=bool(filters.get("currently_on_leave")),
                        )
                        metrics = None
                    elif context.last_intent == "leave_requests":
                        intent = QueryIntent(intent="leave_requests", scope="all")
                        metrics = None
                    else:
                        intent = _deterministic_intent(question, employees)
                        metrics = None
                        if intent is None:
                            intent, metrics = parse_intent(
                                question,
                                context=context,
                            )
                            intent = _apply_deterministic_routing(
                                question,
                                intent,
                                employees,
                            )
                else:
                    intent = _deterministic_intent(question, employees)
                    metrics = None
                    if intent is None:
                        intent, metrics = parse_intent(
                            question,
                            context=context,
                        )
                        intent = _apply_deterministic_routing(
                            question,
                            intent,
                            employees,
                        )
                    intent = _deterministic_intent(question, employees)
            metrics = None

            if intent is None:
                intent, metrics = parse_intent(
                    question,
                    context=context,
                )

                intent = _apply_deterministic_routing(
                    question,
                    intent,
                    employees,
                )

        if intent.intent == "greeting":
            intent = QueryIntent(intent="clarify", scope="single")

        # A terse follow-up after a document answer continues that document.
        # Only replace intents that could otherwise fall through to the
        # worksheet, and only when a continuation cue and document context are
        # present without any structured-data anchor.
        _is_doc_followup = is_document_follow_up(
            question,
            leave_types=_leave_type_names(employees),
            department_names=_department_names(employees),
        )

        if context.last_document_name and _is_doc_followup:
            if intent.intent in {"leave_policy", "clarify", "unsupported"}:
                logger.info("Routed document follow-up to active document scope.")
                intent = QueryIntent(intent="document_question", scope="single")

            elif intent.intent == "leave_balance" and not (
                context.last_employee_id
                and context.last_intent == "leave_balance"
            ):
                logger.info(
                    "Routed document follow-up to active document scope "
                    "(corrected leave_balance)."
                )
                intent = QueryIntent(intent="document_question", scope="single")

            elif intent.intent == "leave_balance" and (
                context.last_employee_id
                and context.last_intent == "leave_balance"
            ):
                logger.info(
                    "Ambiguous follow-up after balance; requesting clarification."
                )
                intent = QueryIntent(intent="clarify", scope="single")

        # The worksheet stores only annual days, accrual, and payment.
        # Questions about other attributes must not be answered with
        # unrelated worksheet fields.
        if (
            intent.intent == "leave_policy"
            and asks_unstructured_policy_detail(question)
        ):
            if documents is not None and not documents.is_empty():
                logger.info(
                    "Routed unstructured policy detail to uploaded documents."
                )
                intent = QueryIntent(intent="document_question", scope="single")
            else:
                unavailable_policy_detail = True

        employee_names = _employee_names(employees)
        leave_types = _leave_type_names(employees)
        department_names = _department_names(employees)

        if (
            intent.intent != "document_question"
            and (
                is_leave_history_question(question)
                or is_group_leave_history_question(question)
                or (
                    context.last_employee_id
                    and context.last_intent in {"leave_balance", "leave_requests", "employee_lookup"}
                    and re.search(r"\b(?:what\s+about|how\s+about)\b.*\bleave\b", question, re.IGNORECASE)
                    and not detect_department_name(question, department_names)
                    and not is_group_leave_history_question(question)
                )
            )
            and intent.intent
            in {
                "leave_balance",
                "leave_requests",
                "department_summary",
                "clarify",
                "unsupported",
            }
            and (
                not detect_department_name(question, department_names)
                or is_group_leave_history_question(question)
            )
            and not asks_currently_on_leave(question)
        ):
            history_status = intent.approval_status
            if history_status is None and re.search(
                r"\b(?:taken|used|took)\b",
                question,
                re.IGNORECASE,
            ):
                history_status = "Approved"

            if is_group_leave_history_question(question):
                logger.info("Leave-history question is group-level.")
                group_history = True
                department = detect_department_name(question, department_names) or intent.department
                currently = getattr(intent, "currently_on_leave", False) or asks_currently_on_leave(question)
                approval_status = intent.approval_status
                if currently and not approval_status:
                    approval_status = "Approved"
                elif not currently:
                    approval_status = None
                intent = QueryIntent(
                    intent="leave_requests",
                    scope="all",
                    department=department,
                    leave_type=(
                        detect_leave_type(question, leave_types)
                        or intent.leave_type
                    ),
                    approval_status=approval_status,
                    start_date=intent.start_date,
                    end_date=intent.end_date,
                    date_mode=getattr(intent, "date_mode", "overlap"),
                    currently_on_leave=currently,
                )
            else:
                employee_id = intent.employee_id
                employee_name = intent.employee_name

                if not employee_id and not employee_name:
                    employee_name = detect_known_employee_name(
                        question,
                        employee_names,
                    )

                if not employee_id and not employee_name:
                    employee_match = re.search(
                        r"\bEMP\d+\b",
                        question,
                        re.IGNORECASE,
                    )
                    if employee_match:
                        employee_id = employee_match.group(0).upper()

                if (
                    not employee_id
                    and not employee_name
                    and context.last_employee_id
                    and context.last_intent
                    in {"leave_balance", "leave_requests", "employee_lookup"}
                    and not (context.last_document_name and _is_doc_followup)
                ):
                    employee_id = context.last_employee_id

                if employee_id or employee_name:
                    detected_lt = detect_leave_type(question, leave_types)
                    intent = QueryIntent(
                        intent="leave_requests",
                        scope="single",
                        employee_id=employee_id,
                        employee_name=employee_name,
                        leave_type=detected_lt or intent.leave_type,
                        approval_status=history_status,
                    )
                    if detected_lt and (employee_id or employee_name):
                        try:
                            reqs = requests.list_requests(
                                employee_id=employee_id,
                                leave_type=detected_lt,
                                approval_status=history_status,
                                limit=1,
                            )
                            if reqs.total_matches == 0:
                                emp_id_res = employee_id
                                if not emp_id_res and employee_name:
                                    try:
                                        emp_id_res = employees.find_by_name(
                                            employee_name
                                        ).employee.employee_id
                                    except Exception:
                                        emp_id_res = None
                                if emp_id_res:
                                    bals = balances.get_balances(
                                        emp_id_res, leave_type=detected_lt
                                    )
                                    if getattr(bals, "balances", None):
                                        intent = QueryIntent(
                                            intent="leave_balance",
                                            scope="single",
                                            employee_id=emp_id_res,
                                            leave_type=detected_lt,
                                        )
                        except Exception:
                            pass
                else:
                    logger.info(
                        "Leave-history question has no employee; clarifying."
                    )
                    history_needs_employee = True
                    intent = QueryIntent(intent="clarify", scope="single")

        if intent.intent in {"leave_requests", "department_summary"}:
            if asks_submission_date(question):
                logger.info(
                    "Submission-date filter requested; field is unavailable."
                )
                submission_date_unavailable = True
            else:
                try:
                    detected_range = detect_leave_date_range(question)
                except InvalidFilterError as exc:
                    raise HTTPException(
                        status_code=422,
                        detail=str(exc),
                    ) from exc

                if detected_range:
                    start_date, end_date = detected_range
                    updates = {}
                    if start_date:
                        updates["start_date"] = start_date
                    if end_date:
                        updates["end_date"] = end_date
                    date_mode = "overlap"
                    if _START_DATE_RE.search(question):
                        date_mode = "start_date"
                    elif _END_DATE_RE.search(question):
                        date_mode = "end_date"
                    updates["date_mode"] = date_mode
                    if updates:
                        intent = intent.model_copy(update=updates)

            if intent.intent == "leave_requests":
                ql = question.lower()
                if intent.approval_status is None:
                    if re.search(r"\b(only\s+)?approved\b", ql):
                        intent = intent.model_copy(update={"approval_status": "Approved"})
                    elif re.search(r"\b(only\s+)?pending\b", ql):
                        intent = intent.model_copy(update={"approval_status": "Pending"})
                    elif re.search(r"\b(only\s+)?rejected\b", ql) or re.search(r"\breject(?:ed)?\b", ql):
                        intent = intent.model_copy(update={"approval_status": "Rejected"})
                    elif re.search(r"\bcancel(?:led|ed)\b", ql):
                        intent = intent.model_copy(update={"approval_status": "Cancelled"})

        if intent.intent in {
            "leave_requests",
            "leave_balance",
            "leave_policy",
            "department_summary",
            "department_balance_summary",
        }:
            unsupported_leave_type = detect_unsupported_leave_type(
                question,
                leave_types,
            )
            if unsupported_leave_type:
                available = ", ".join(sorted(leave_types))
                raise HTTPException(
                    status_code=422,
                    detail=(
                        f"The workbook has no policy or balance records for "
                        f"'{unsupported_leave_type}'. Available leave types: "
                        f"{available}."
                    ),
                )

        mentions = extract_document_mentions(question)

        # Casual/leave-type follow-up: resolve employee from context and preserve
        # the previous task (balance vs requests); clarify if truly ambiguous.
        lowered = question.lower()
        if (
            (
                "what about" in lowered
                or "how about" in lowered
                or re.search(r"\bwhat is (?:his|her|their)\b", lowered)
            )
            and "leave" in lowered
            and context.last_employee_id
            and intent.intent in {"leave_requests", "leave_balance", "clarify"}
        ):
            detected_lt = detect_leave_type(question, leave_types) or intent.leave_type
            emp_id = context.last_employee_id
            emp_name = context.last_employee_name
            if not emp_name:
                try:
                    emp_name = employees.get_employee(emp_id).employee.full_name
                except Exception:
                    emp_name = None
            name_display = f"{emp_name} ({emp_id})" if emp_name else emp_id

            is_balance_wording = bool(re.search(r"\b(?:balance|balances|remaining|days?\s+left|available|entitlement)\b", question, re.I))
            is_requests_wording = bool(re.search(r"\b(?:requests?|history|taken|used|took|applied|application|approved|pending|rejected)\b", question, re.I))

            if is_balance_wording:
                intent = QueryIntent(
                    intent="leave_balance",
                    scope="single",
                    employee_id=emp_id,
                    leave_type=detected_lt,
                )
            elif is_requests_wording:
                intent = QueryIntent(
                    intent="leave_requests",
                    scope="single",
                    employee_id=emp_id,
                    leave_type=detected_lt,
                )
            elif context.last_intent == "leave_balance":
                intent = QueryIntent(
                    intent="leave_balance",
                    scope="single",
                    employee_id=emp_id,
                    leave_type=detected_lt,
                )
            elif context.last_intent == "leave_requests":
                # Ambiguous follow-up: distinguish leave balance from request history
                # and return a targeted clarification instead of an empty result.
                targeted_clarification = (
                    f"Would you like to see {name_display}'s {detected_lt or 'leave'} balance "
                    f"or their leave request history?"
                )
                intent = QueryIntent(
                    intent="clarify",
                    scope="single",
                    employee_id=emp_id,
                    leave_type=detected_lt,
                )
            else:
                intent = QueryIntent(intent="clarify", scope="single")
        threshold_spec = detect_balance_threshold(question)
        threshold = threshold_spec.get("value") if threshold_spec else None
        threshold_operator = threshold_spec.get("operator") if threshold_spec else None
        employee_specific = bool(
            intent.employee_id
            or intent.employee_name
            or detect_known_employee_name(question, employee_names)
            or re.search(r"\bEMP\d+\b", question, re.IGNORECASE)
        )
        if (
            threshold is not None
            and not employee_specific
            and intent.intent not in {"document_question", "leave_policy"}
        ):
            leave_type = (
                detect_leave_type(question, leave_types)
                or intent.leave_type
            )
            by_department = is_department_breakdown_question(question)
            department = None
            if not by_department:
                department = (
                    detect_department_name(question, department_names)
                    or intent.department
                )

            result = balances.filter_remaining_balances(
                threshold=threshold,
                threshold_operator=threshold_operator,
                leave_type=leave_type,
                department=department,
                by_department=by_department,
            )
            if not by_department:
                result["count_only"] = is_balance_count_question(question)

            intent = QueryIntent(
                intent="leave_balance",
                scope=(
                    "all"
                    if by_department or not department
                    else "department"
                ),
                department=department,
                leave_type=leave_type,
            )
            metrics = None
            threshold_handled = True

        # An explicit comparison is not ambiguity. Two named files are used
        # directly; a terse follow-up reuses the pair from the last successful
        # comparison. Anything else reaches RAG without guessed targets.
        if is_document_comparison_request(question, mentions):
            compared = True
            unavailable_policy_detail = False

            if len(mentions) == 2:
                comparison_names = list(mentions)
                intent = QueryIntent(intent="document_question", scope="single")
                logger.info("Routed explicit two-document comparison.")
            elif not mentions and len(context.last_compared_document_names) == 2:
                comparison_names = list(context.last_compared_document_names)
                intent = QueryIntent(intent="document_question", scope="single")
                logger.info(
                    "Routed comparison follow-up to remembered documents."
                )
            elif (
                not mentions
                and documents is not None
                and len(documents.list_all()) == 2
            ):
                comparison_names = [
                    str(document.name)
                    for document in documents.list_all()
                ]
                intent = QueryIntent(intent="document_question", scope="single")
                logger.info(
                    "Routed comparison to the only two registered documents."
                )
            else:
                intent = QueryIntent(intent="document_question", scope="single")
                logger.info("Comparison request has no reliable document pair.")

        # Document-scope precedence: a filename in this question wins; two or
        # more names stay ambiguous; otherwise reuse the document named in the
        # last matched document answer. Injecting here covers both the
        # deterministic branch and the LLM branch.
        if intent.intent == "document_question":
            if len(mentions) == 1:
                document_name = mentions[0]
            elif len(mentions) >= 2 or comparison_names:
                document_name = None
            else:
                document_name = (
                    intent.document_name or context.last_document_name
                )

            intent = intent.model_copy(
                update={"document_name": document_name}
            )

        # Preserve an unambiguous employee-specific balance follow-up: when the
        # user names only another leave type after a balance answer, reuse the
        # active employee instead of asking for the ID again. If an active
        # document is also in play the follow-up is genuinely ambiguous.
        if (
            intent.intent == "leave_balance"
            and getattr(intent, "scope", "single") == "single"
            and not intent.employee_id
            and not intent.employee_name
            and context.last_employee_id
            and context.last_intent == "leave_balance"
        ):
            if context.last_document_name and _is_doc_followup:
                logger.info(
                    "Ambiguous follow-up after balance; requesting clarification."
                )
                intent = QueryIntent(intent="clarify", scope="single")
            else:
                logger.info(
                    "Carried active employee into balance follow-up."
                )
                intent = intent.model_copy(
                    update={"employee_id": context.last_employee_id}
                )

        if (
            not threshold_handled
            and intent.intent in {"leave_requests", "employee_lookup"}
            and not intent.employee_id
            and not intent.employee_name
        ):
            known_name = detect_known_employee_name(
                question,
                employee_names,
            )
            employee_match = re.search(r"\bEMP\d+\b", question, re.IGNORECASE)

            if known_name:
                intent = intent.model_copy(
                    update={"employee_name": known_name}
                )
            elif employee_match:
                intent = intent.model_copy(
                    update={"employee_id": employee_match.group(0).upper()}
                )
            else:
                unresolved_employee = detect_unresolved_employee_reference(
                    question,
                    employee_names=employee_names,
                    department_names=department_names,
                    leave_types=leave_types,
                    approval_statuses=(
                        employees._repo.leave_requests["Approval Status"]
                        .dropna()
                        .astype(str)
                        .unique()
                        .tolist()
                    ),
                )
                if unresolved_employee:
                    candidate_words = unresolved_employee.lower().split()
                    prefix_match = any(
                        all(
                            any(
                                word.startswith(candidate)
                                for word in str(name).lower().split()
                            )
                            for candidate in candidate_words
                        )
                        for name in employee_names
                    )
                    if prefix_match:
                        intent = intent.model_copy(
                            update={"employee_name": unresolved_employee}
                        )
                        unresolved_employee = None

    except GroqParseError as exc:
        logger.warning("Intent parsing failed: %s", exc)

        if (
            "start date must not be later than the end date"
            in str(exc).lower()
        ):
            raise HTTPException(
                status_code=422,
                detail=str(exc),
            ) from exc

        raise HTTPException(
            status_code=exc.status_code,
            detail=str(exc),
        ) from exc

    # If a single-employee balance query has no employee identity,
    # ask directly instead of calling the balance service with a null ID.
    needs_employee_id = (
        intent.intent == "leave_balance"
        and getattr(intent, "scope", "single") == "single"
        and not intent.employee_id
        and not intent.employee_name
    )

    pending_to_set = False

    if history_needs_employee:
        result = {"message": _HISTORY_EMPLOYEE_REQUIRED}
        answer = result["message"]
        data = None
        evidence = None

    elif needs_employee_id:
        result = {
            "message": (
                "Please provide your employee ID "
                "to check your leave balance."
            )
        }

        answer = result["message"]
        data = None
        evidence = None
        pending_to_set = True

    else:
        if threshold_handled:
            pass
        else:
            try:
                if targeted_clarification:
                    result = {"message": targeted_clarification}
                elif submission_date_unavailable:
                    result = {"message": _SUBMISSION_DATE_UNAVAILABLE}
                elif unresolved_employee:
                    result = {
                        "message": (
                            f"I couldn't find an employee named "
                            f"'{unresolved_employee}'. Please provide a valid "
                            "employee ID or full name."
                        )
                    }
                elif unavailable_policy_detail:
                    result = {"message": _POLICY_DETAIL_UNAVAILABLE}
                elif group_history:
                    approval_status = intent.approval_status
                    if getattr(intent, "currently_on_leave", False) and not approval_status:
                        approval_status = "Approved"
                    result = requests.list_requesting_employees(
                        leave_type=intent.leave_type,
                        approval_status=approval_status,
                        start_date=intent.start_date,
                        end_date=intent.end_date,
                        department=intent.department,
                        date_mode=intent.date_mode,
                    )
                else:
                    lowered_q = question.lower()
                    req_limit = limit
                    if re.search(r"\b(show\s+more|next\s+\d+|more\s+results)\b", lowered_q):
                        req_limit = (limit or 50) * 3
                        if req_limit < 30:
                            req_limit = 30
                    result = dispatch_query(
                        intent,
                        employees,
                        requests,
                        balances,
                        policies,
                        departments,
                        question=question,
                        documents=documents,
                        settings=settings,
                        document_names=comparison_names,
                        limit=req_limit,
                    )

            except AppError:
                raise

            except Exception as exc:
                logger.exception(
                    "Unexpected error during dispatch for intent '%s'.",
                    intent.intent,
                )
                raise HTTPException(
                    status_code=500,
                    detail="An unexpected error occurred. Please try again.",
                ) from exc

        if isinstance(result, dict) and result.get("group_history"):
            answer, data, evidence = format_group_leave_history(result)
        else:
            answer, data, evidence = format_response(
                intent.intent,
                result,
                count_only=is_balance_count_question(question),
            )

    return _PreparedAnswer(
        conversation_id=resolved_id,
        context=context,
        intent=intent,
        metrics=metrics,
        result=result,
        answer=answer,
        data=data,
        evidence=evidence,
        question=question,
        resolved_pending=resolved_pending,
        pending_to_set=pending_to_set,
        compared=compared,
    )


def _commit_answer(prepared: _PreparedAnswer) -> None:
    # Only a complete answer is committed to the conversation.
    conversation_service.add_message(
        prepared.context,
        "assistant",
        prepared.answer,
    )

    if prepared.resolved_pending:
        conversation_service.clear_pending_clarification(
            prepared.context,
        )

    if prepared.intent.intent not in {"greeting", "help"}:
        try:
            if prepared.intent.intent == "leave_requests":
                pass
            else:
                conversation_service.update_from_result(
                    prepared.context,
                    prepared.intent.intent,
                    prepared.result,
                    scope=getattr(prepared.intent, "scope", "single"),
                    compared=prepared.compared,
                )
        except Exception:
            conversation_service.update_from_result(
                prepared.context,
                prepared.intent.intent,
                prepared.result,
                scope=getattr(prepared.intent, "scope", "single"),
                compared=prepared.compared,
            )

    if prepared.pending_to_set:
        conversation_service.set_pending_clarification(
            prepared.context,
            intent="leave_balance",
            question=prepared.question,
            field_name="employee_id",
            leave_type=prepared.intent.leave_type,
            department=prepared.intent.department,
        )

    try:
        if prepared.intent.intent == "leave_requests":
            filters = getattr(prepared.intent, "__dict__", {})
            applied = {}
            for k in ["employee_id", "employee_name", "leave_type", "approval_status", "start_date", "end_date", "department", "date_mode", "currently_on_leave"]:
                v = getattr(prepared.intent, k, None)
                if v is not None and v != "":
                    if hasattr(v, "isoformat"):
                        applied[k] = v.isoformat()
                    else:
                        applied[k] = v
            conversation_service.update_from_result(
                prepared.context,
                prepared.intent.intent,
                prepared.result,
                scope=getattr(prepared.intent, "scope", "single"),
                compared=prepared.compared,
                filters=applied,
            )
    except Exception:
        pass


def _chat_response(prepared: _PreparedAnswer) -> ChatResponse:
    return ChatResponse(
        answer=prepared.answer,
        intent=prepared.intent.intent,
        data=prepared.data,
        evidence=prepared.evidence,
        conversation_id=prepared.conversation_id,
        metrics=(
            LLMMetrics(**prepared.metrics)
            if prepared.metrics
            else None
        ),
    )


@router.post(
    "/chat",
    response_model=ChatResponse,
    summary="Ask a leave management question",
)
def chat(
    request: Request,
    body: ChatRequest,
    employees: EmployeeService = Depends(get_employee_service),
    requests: LeaveRequestService = Depends(get_leave_request_service),
    balances: BalanceService = Depends(get_balance_service),
    policies: PolicyService = Depends(get_policy_service),
    departments: DepartmentService = Depends(get_department_service),
) -> ChatResponse:
    prepared = _prepare_answer(
        body.question,
        body.conversation_id,
        employees,
        requests,
        balances,
        policies,
        departments,
        getattr(request.app.state, "document_registry", None),
        get_settings(),
        limit=body.limit,
    )

    response = _chat_response(prepared)
    _commit_answer(prepared)

    return response


@router.post(
    "/chat/stream",
    summary="Ask a leave management question and stream the answer",
    response_class=StreamingResponse,
)
async def chat_stream(
    request: Request,
    body: ChatRequest,
    employees: EmployeeService = Depends(get_employee_service),
    requests: LeaveRequestService = Depends(get_leave_request_service),
    balances: BalanceService = Depends(get_balance_service),
    policies: PolicyService = Depends(get_policy_service),
    departments: DepartmentService = Depends(get_department_service),
) -> StreamingResponse:
    prepared = await run_in_threadpool(
        _prepare_answer,
        body.question,
        body.conversation_id,
        employees,
        requests,
        balances,
        policies,
        departments,
        getattr(request.app.state, "document_registry", None),
        get_settings(),
        limit=body.limit,
    )

    return StreamingResponse(
        stream_answer(
            request,
            prepared.conversation_id,
            prepared.intent.intent,
            prepared.answer,
            lambda: _chat_response(prepared).model_dump(mode="json"),
            lambda: _commit_answer(prepared),
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
