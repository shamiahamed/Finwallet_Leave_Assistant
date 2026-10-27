
from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
from typing import Any


MAX_HISTORY_MESSAGES = 10
MAX_CONVERSATIONS = 500

NON_EMPLOYEE_INTENTS = {
    "employee_headcount",
    "leave_policy",
    "department_summary",
    "document_question",
}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_employee_id(value: str | None) -> str | None:
    if not value:
        return None

    value = value.strip().upper()

    if re.fullmatch(r"EMP\d+", value):
        return value

    return None


@dataclass
class ConversationContext:
    conversation_id: str
    last_employee_id: str | None = None
    last_employee_name: str | None = None
    last_manager_id: str | None = None
    last_manager_name: str | None = None
    last_intent: str | None = None
    last_document_id: str | None = None
    last_document_name: str | None = None
    last_compared_document_names: list[str] = field(default_factory=list)

    # The application stores the task awaiting a clarification.
    pending_intent: str | None = None
    pending_question: str | None = None
    pending_field: str | None = None
    pending_leave_type: str | None = None
    pending_department: str | None = None

    last_request_filters: dict[str, Any] = field(default_factory=dict)
    last_request_offset: int = 0
    last_request_ids: list[str] = field(default_factory=list)

    history: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=_now)
    updated_at: datetime = field(default_factory=_now)


class ConversationService:
    """In-memory conversation store, cleared when the backend restarts."""

    def __init__(self) -> None:
        self._conversations: dict[str, ConversationContext] = {}

    def get_or_create(self, conversation_id: str) -> ConversationContext:
        if conversation_id not in self._conversations:
            self._evict_oldest_if_full()
            self._conversations[conversation_id] = ConversationContext(
                conversation_id=conversation_id
            )

        return self._conversations[conversation_id]

    def add_message(
        self,
        context: ConversationContext,
        role: str,
        content: str,
    ) -> None:
        context.history.append(
            {
                "role": role,
                "content": content,
                "timestamp": _now().isoformat(),
            }
        )
        context.history = context.history[-MAX_HISTORY_MESSAGES:]
        context.updated_at = _now()

    def set_pending_clarification(
        self,
        context: ConversationContext,
        *,
        intent: str,
        question: str,
        field_name: str = "employee_id",
        leave_type: str | None = None,
        department: str | None = None,
    ) -> None:
        """Remember the original task while asking the user for missing data."""
        context.pending_intent = intent
        context.pending_question = question
        context.pending_field = field_name
        context.pending_leave_type = leave_type
        context.pending_department = department
        context.updated_at = _now()

    def clear_pending_clarification(
        self,
        context: ConversationContext,
    ) -> None:
        context.pending_intent = None
        context.pending_question = None
        context.pending_field = None
        context.pending_leave_type = None
        context.pending_department = None
        context.updated_at = _now()

    def resolve_pending_employee_id(
        self,
        context: ConversationContext,
        message: str,
    ) -> dict[str, str | None] | None:
        """
        Resolve an ID-only reply when the application is waiting for an ID.

        Returns the stored task if the message is a valid ID.
        Does not clear the task; the caller should validate the employee
        and clear the task only after successful resolution.
        """
        if (
            context.pending_field != "employee_id"
            or not context.pending_intent
        ):
            return None

        employee_id = normalize_employee_id(message)

        if not employee_id:
            return None

        return {
            "intent": context.pending_intent,
            "question": context.pending_question,
            "employee_id": employee_id,
            "leave_type": context.pending_leave_type,
            "department": context.pending_department,
        }

    def update_from_result(
        self,
        context: ConversationContext,
        intent: str,
        result: Any,
        scope: str = "single",
        compared: bool = False,
        filters: dict[str, Any] | None = None,
    ) -> None:
        context.last_intent = intent
        context.updated_at = _now()

        # Document scope comes from the answer itself and must be updated
        # before any early return below can skip it. A matched answer citing
        # one document sets the scope; several documents clear it; an answer
        # without evidence (ambiguous, missing, insufficient) keeps it.
        if self._is_document_result(result):
            self._update_document_scope(context, result)

            if compared and result.get("matched"):
                self._update_compared_documents(context, result)
            else:
                self._clear_compared_documents(context)
        else:
            self._clear_document_scope(context)
            self._clear_compared_documents(context)

        try:
            if intent == "leave_requests" and isinstance(result, dict):
                if filters:
                    context.last_request_filters = dict(filters)
                else:
                    context.last_request_filters = dict(result.get("filters_applied") or {})
                reqs = result.get("requests") or []
                ids = []
                for r in reqs:
                    if isinstance(r, dict) and r.get("request_id"):
                        ids.append(r["request_id"])
                context.last_request_ids = ids
                context.last_request_offset = len(ids)
        except Exception:
            pass

        # A broad result must not preserve a previously active employee.
        if intent in NON_EMPLOYEE_INTENTS or (
            intent == "leave_balance"
            and scope in {"all", "department"}
        ):
            self._clear_active_employee(context)
            return

        new_employee_id = None
        new_employee_name = None
        new_manager_id = None
        new_manager_name = None

        employee = getattr(result, "employee", None)

        if employee is not None:
            new_employee_id = getattr(employee, "employee_id", None)
            new_employee_name = getattr(employee, "full_name", None)
            new_manager_id = getattr(employee, "manager_id", None)
            new_manager_name = getattr(employee, "manager_name", None)

        elif getattr(result, "employee_id", None):
            new_employee_id = result.employee_id
            new_employee_name = getattr(result, "employee_name", None)

            manager = getattr(result, "manager", None)
            if manager is not None:
                new_manager_id = getattr(manager, "employee_id", None)
                new_manager_name = getattr(manager, "full_name", None)

        else:
            requests = getattr(result, "requests", None)

            if requests:
                employee_ids = {
                    getattr(item, "employee_id", None)
                    for item in requests
                }
                employee_ids.discard(None)

                if len(employee_ids) == 1:
                    new_employee_id = next(iter(employee_ids))
                    first = requests[0]
                    new_employee_name = getattr(
                        first, "employee_name", None
                    )

        if new_employee_id is None:
            return

        if new_employee_id != context.last_employee_id:
            context.last_manager_id = None
            context.last_manager_name = None

        context.last_employee_id = new_employee_id
        context.last_employee_name = new_employee_name

        if new_manager_id is not None:
            context.last_manager_id = new_manager_id
            context.last_manager_name = new_manager_name

    @staticmethod
    def _is_document_result(result: Any) -> bool:
        """True only for the retrieval result shape.

        Structured services return models, and helper responses return a dict
        containing only ``message``. Requiring all three retrieval keys avoids
        treating those dicts as document answers.
        """
        return (
            isinstance(result, dict)
            and "answer" in result
            and "matched" in result
            and "sources" in result
        )

    def _update_document_scope(
        self,
        context: ConversationContext,
        result: dict,
    ) -> None:
        # Ambiguous, missing, and insufficient-evidence answers carry no
        # matched sources, so the previously selected document stays active.
        if not result.get("matched"):
            return

        document_ids: list[str] = []
        names: dict[str, str | None] = {}

        for source in result.get("sources") or []:
            if not isinstance(source, dict):
                continue

            document_id = source.get("document_id")

            if not document_id:
                continue

            if document_id not in names:
                document_ids.append(document_id)
                names[document_id] = source.get("document_name")

        if len(document_ids) == 1:
            document_id = document_ids[0]
            context.last_document_id = document_id
            context.last_document_name = names.get(document_id)
        elif len(document_ids) > 1:
            self._clear_document_scope(context)

    @staticmethod
    def _update_compared_documents(
        context: ConversationContext,
        result: dict,
    ) -> None:
        """Remember the two documents from a successful comparison.

        Only a pair is stored. Anything else clears the context so a later
        "compare both documents" cannot guess.
        """
        names: list[str] = []
        seen_ids: set[str] = set()

        for source in result.get("sources") or []:
            if not isinstance(source, dict):
                continue

            document_id = source.get("document_id")
            document_name = source.get("document_name")

            if not document_id or not document_name:
                continue

            if document_id in seen_ids:
                continue

            seen_ids.add(document_id)
            names.append(document_name)

        context.last_compared_document_names = names if len(names) == 2 else []

    @staticmethod
    def _clear_document_scope(context: ConversationContext) -> None:
        context.last_document_id = None
        context.last_document_name = None

    @staticmethod
    def _clear_compared_documents(context: ConversationContext) -> None:
        context.last_compared_document_names = []

    @staticmethod
    def _clear_active_employee(context: ConversationContext) -> None:
        context.last_employee_id = None
        context.last_employee_name = None
        context.last_manager_id = None
        context.last_manager_name = None

    def _evict_oldest_if_full(self) -> None:
        if len(self._conversations) < MAX_CONVERSATIONS:
            return

        oldest_id = min(
            self._conversations,
            key=lambda cid: self._conversations[cid].updated_at,
        )
        del self._conversations[oldest_id]
