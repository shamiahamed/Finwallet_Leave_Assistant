from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Maximum leave requests shown inline in the answer text 
_INLINE_REQUEST_LIMIT = 5


def format_response(
    intent: str,
    result: Any,
    *,
    count_only: bool = False,
) -> tuple[str, dict | list | None, dict | None]:

    # Serialise the result once so formatters work with plain dicts
    if isinstance(result, BaseModel):
        serialised = result.model_dump(mode="json")
    elif isinstance(result, dict):
        serialised = dict(result)  # shallow copy to avoid mutating caller data
    else:
        serialised = result

    # A retrieval result may arrive under an unsupported/clarify label when the
    # question was re-routed to documents; format it as a document answer.
    if isinstance(serialised, dict) and "answer" in serialised and "matched" in serialised:
        intent = "document_question"

    if intent == "leave_requests" and isinstance(serialised, dict):
        return _format_leave_requests(serialised, count_only=count_only)

    # Dispatch to the right formatter
    formatters = {
        "employee_lookup": _format_employee,
        "employee_list": _format_employee_list,
        "employee_headcount": _format_headcount,
        "leave_requests": _format_leave_requests,
        "leave_balance": _format_leave_balance,
        "department_balance_summary": _format_department_balance_summary,
        "leave_policy": _format_leave_policy,
        "department_summary": _format_department_summary,
        "document_question": _format_document_answer,
        "help": _format_plain_message,
        "clarify": _format_clarify,
        "unsupported": _format_unsupported,
    }

    formatter = formatters.get(intent)
    if formatter is None:
        logger.warning("No formatter registered for intent '%s'.", intent)
        return _format_plain_message(serialised)

    return formatter(serialised)


# Formatters

def _extract_evidence(data: dict) -> tuple[dict, dict | None]:
    
    evidence = data.pop("evidence", None)
    return data, evidence


def _format_plain_message(data: Any) -> tuple[str, Any, None]:
    
    if isinstance(data, dict):
        answer = data.get("message", "Your request has been processed.")
        return answer, data, None
    return "Your request has been processed.", data, None


def _format_employee(data: dict) -> tuple[str, dict | list | None, dict | None]:
    # Dispatcher returns a plain dict with 'message' when no ID/name was given.
    if "message" in data and "employee" not in data:
        return data["message"], None, None

    data, evidence = _extract_evidence(data)
    emp = data.get("employee", {})

    name = emp.get("full_name", "Unknown")
    eid = emp.get("employee_id", "?")
    dept = emp.get("department", "Unknown")
    designation = emp.get("designation", "")
    status = emp.get("employment_status", "")
    office = emp.get("office", "")
    manager = emp.get("manager_name") or emp.get("manager_id") or "None"

    answer = (
        f"{name} (ID: {eid}) works in {dept} as {designation}. "
        f"Status: {status}. Office: {office}. Manager: {manager}."
    )
    return answer, data, evidence


def _format_employee_list(data: dict) -> tuple[str, dict | list | None, dict | None]:
    if "message" in data and "employees" not in data:
        return data["message"], None, None
    data, evidence = _extract_evidence(data)
    employees = data.get("employees", [])
    total = data.get("total_matches", len(employees))
    returned = data.get("returned", len(employees))
    if not employees:
        return "No employees found matching your filters.", data, evidence
    employee_word = "employee" if total == 1 else "employees"
    lines = [f"Found {total} {employee_word}:"]
    for emp in employees:
        lines.append(f"  • {emp.get('full_name','?')} ({emp.get('employee_id','?')}) - {emp.get('department','?')}")
    if total > returned:
        lines.append(f"  • showing first {returned} of {total}.")
    return "\n".join(lines), data, evidence


def _format_headcount(data: dict) -> tuple[str, dict | list | None, dict | None]:
    if "message" in data and "count" not in data:
        return data["message"], None, None

    data, evidence = _extract_evidence(data)
    count = data.get("count", 0)
    dept = data.get("department")
    status = data.get("employment_status")

    label_parts: list[str] = []
    if status:
        label_parts.append(status.lower())
    label_parts.append("employee" if count == 1 else "employees")
    if dept:
        label_parts.append(f"in {dept}")

    label = " ".join(label_parts)
    answer = f"There {'is' if count == 1 else 'are'} {count} {label}."
    return answer, data, evidence


def _format_leave_requests(
    data: dict,
    *,
    count_only: bool = False,
) -> tuple[str, dict | list | None, dict | None]:
    if "message" in data and "requests" not in data:
        return data["message"], None, None

    data, evidence = _extract_evidence(data)
    total = data.get("total_matches", 0)
    total_days = data.get("total_days", 0)
    requests = data.get("requests", [])
    truncated = data.get("truncated", False)

    if total == 0:
        answer = "No leave requests were found matching your filters."
        return answer, data, evidence

    # Build a short summary 
    request_word = "request" if total == 1 else "requests"
    day_word = "day" if total_days == 1 else "days"
    answer = f"Found {total} leave {request_word} totalling {total_days} {day_word}."

    # Name the employee if there is only one.
    if requests:
        first = requests[0]
        name = first.get("employee_name", "")
        if name and all(r.get("employee_name") == name for r in requests):
            answer = f"{name} has {total} leave {request_word} totalling {total_days} {day_word}."

    if count_only:
        return answer, data, evidence

    # Summarise the first few requests.
    shown = requests[:_INLINE_REQUEST_LIMIT]
    if shown:
        lines = []
        for req in shown:
            rid = req.get("request_id", "?")
            lt = req.get("leave_type", "")
            sd = req.get("start_date", "?")
            ed = req.get("end_date", "?")
            days = req.get("days", "?")
            day_word = "day" if days == 1 else "days"
            st = req.get("approval_status", "?")
            lines.append(
                f"  • {rid}: {lt} from {sd} to {ed} ({days} {day_word}, {st})"
            )
        answer += "\n" + "\n".join(lines)

    if total > len(shown):
        answer += f"\n  (Showing first {len(shown)} of {total} matching requests.)"

    return answer, data, evidence


def format_group_leave_history(
    data: dict,
) -> tuple[str, dict | list | None, dict | None]:
    serialised = dict(data)
    evidence = serialised.pop("evidence", None)
    employees = serialised.get("employees", [])

    if not employees:
        return (
            "No employees had matching leave requests in the requested period.",
            serialised,
            evidence,
        )

    total = serialised.get("total_employees", len(employees))
    employee_word = "employee" if total == 1 else "employees"
    lines = [f"{total} {employee_word} had matching leave requests:"]
    for employee in employees:
        name = employee.get("employee_name", "Unknown")
        eid = employee.get("employee_id", "?")
        department = employee.get("department", "Unknown")
        request_count = employee.get("request_count", 0)
        total_days = employee.get("total_days", 0)
        request_word = "request" if request_count == 1 else "requests"
        day_word = "day" if total_days == 1 else "days"
        lines.append(
            f"  • {name} ({eid}) - {department}: "
            f"{request_count} {request_word}, {total_days} {day_word}"
        )

    return "\n".join(lines), serialised, evidence


def _format_leave_balance(data: dict) -> tuple[str, dict | list | None, dict | None]:
    if data.get("threshold_filter"):
        return _format_remaining_balances(data)

    # Dispatcher returns a plain dict with 'message' when no ID was given.
    if "message" in data and "balances" not in data and "results" not in data:
        return data["message"], None, None

    # Broadcast scopes return a container of per-employee balances.
    if data.get("scope") == "all":
        return _format_all_balances(data)

    if data.get("scope") == "department":
        return _format_department_balances(data)

    data, evidence = _extract_evidence(data)
    name = data.get("employee_name", "The employee")
    eid = data.get("employee_id", "?")
    balances: list[dict] = data.get("balances", [])
    note = data.get("note")

    if not balances:
        answer = f"No balance records found for {name} ({eid})."
    else:
        lines = [f"Leave balances for {name} ({eid}):"]
        for b in balances:
            lt = b.get("leave_type", "?")
            yr = b.get("year", "?")
            entitlement = b.get("annual_entitlement", 0)
            used = b.get("approved_days_used", 0)
            remaining = b.get("remaining_days", 0)
            lines.append(
                f"  • {lt} ({yr}): {entitlement} days entitlement, "
                f"{used} used, {remaining} remaining."
            )
        answer = "\n".join(lines)

    if note:
        answer += f"\n\nNote: {note}"

    return answer, data, evidence


def _format_remaining_balances(
    data: dict,
) -> tuple[str, dict | list | None, dict | None]:
    data, evidence = _extract_evidence(data)
    threshold = data.get("threshold", 0)
    threshold_operator = data.get("threshold_operator", "at_most")
    leave_type = data.get("leave_type")
    balance_label = leave_type or "leave"

    if threshold_operator == "exactly":
        condition = f"exactly {threshold} {balance_label} days remaining"
    elif threshold_operator == "less_than":
        condition = f"less than {threshold} {balance_label} days remaining"
    elif threshold == 0:
        condition = f"zero remaining {balance_label}"
    else:
        condition = f"{threshold} or fewer {balance_label} days remaining"

    missing_count = int(data.get("missing_count", 0))
    note = None
    if missing_count:
        employee_word = "employee" if missing_count == 1 else "employees"
        verb = "has" if missing_count == 1 else "have"
        counted_verb = "was" if missing_count == 1 else "were"
        note = (
            f"{missing_count} {employee_word} {verb} no matching "
            f"{balance_label} balance record and {counted_verb} not counted."
        )

    if data.get("count_by_department"):
        total_matching = int(data.get("total_matching", 0))
        if total_matching:
            answer = f"Employees with {condition}, by department:"
        else:
            answer = f"No employees have {condition} in any department."

        lines = []
        for department in data.get("departments", []):
            line = f"  • {department.get('department', '?')}: {department.get('count', 0)}"
            missing = int(department.get("missing_balance_records", 0))
            if missing:
                line += f" ({missing} with no balance record)"
            lines.append(line)

        if lines:
            answer += "\n" + "\n".join(lines)
        if note:
            answer += f"\n\nNote: {note}"
        return answer, data, evidence

    results: list[dict] = data.get("results", [])
    if not results:
        answer = f"No employees have {condition}."
    elif data.get("count_only"):
        employee_word = "employee" if len(results) == 1 else "employees"
        answer = (
            f"There {'is' if len(results) == 1 else 'are'} "
            f"{len(results)} {employee_word} with {condition}."
        )
    else:
        answer = "\n".join(
            [f"Employees with {condition} ({len(results)}):", *_format_balance_lines(results)]
        )

    if note:
        answer += f"\n\nNote: {note}"

    return answer, data, evidence


def _format_balance_lines(results: list[dict]) -> list[str]:
    lines: list[str] = []
    for employee in results:
        name = employee.get("employee_name", "Unknown")
        eid = employee.get("employee_id", "?")
        balances = employee.get("balances", [])

        if not balances:
            lines.append(f"  • {name} ({eid}): no balance records.")
            continue

        if len(balances) == 1:
            b = balances[0]
            lines.append(
                f"  • {name} ({eid}): {b.get('leave_type', '?')} "
                f"({b.get('year', '?')}) - {b.get('remaining_days', 0)} remaining "
                f"of {b.get('annual_entitlement', 0)}."
            )
            continue

        lines.append(f"  • {name} ({eid}):")
        for b in balances:
            lines.append(
                f"      - {b.get('leave_type', '?')} ({b.get('year', '?')}): "
                f"{b.get('remaining_days', 0)} remaining of "
                f"{b.get('annual_entitlement', 0)}."
            )
    return lines


def _format_all_balances(data: dict) -> tuple[str, dict | list | None, dict | None]:
    data, evidence = _extract_evidence(data)
    results: list[dict] = data.get("results", [])
    total = data.get("total_employees", len(results))
    note = data.get("note")

    if not results:
        return "No employee balance records were found.", data, evidence

    header = f"Leave balances for all {total} employee(s):"
    answer = "\n".join([header, *_format_balance_lines(results)])

    if note:
        answer += f"\n\nNote: {note}"

    return answer, data, evidence


def _format_department_balances(data: dict) -> tuple[str, dict | list | None, dict | None]:
    data, evidence = _extract_evidence(data)
    department = data.get("department", "?")
    results: list[dict] = data.get("results", [])
    total = data.get("total_employees", len(results))
    note = data.get("note")

    if not results:
        answer = f"No employees were found in {department}."
        if note:
            answer += f"\n\nNote: {note}"
        return answer, data, evidence

    header = f"Leave balances for {department} ({total} employee(s)):"
    answer = "\n".join([header, *_format_balance_lines(results)])

    if note:
        answer += f"\n\nNote: {note}"

    return answer, data, evidence


def _format_leave_policy(data: dict) -> tuple[str, dict | list | None, dict | None]:
    if "message" in data and "policies" not in data:
        return data["message"], None, None

    data, evidence = _extract_evidence(data)
    policies: list[dict] = data.get("policies", [])

    if not policies:
        answer = "No leave policy information was found."
        return answer, data, evidence

    lines = ["Leave policies:"]
    for p in policies:
        lt = p.get("leave_type", "?")
        days = p.get("annual_days", "?")
        accrual = p.get("accrual", "?")
        payment = p.get("payment", "?")
        lines.append(f"  • {lt}: {days} days/year. Accrual: {accrual}. Payment: {payment}.")

    answer = "\n".join(lines)
    return answer, data, evidence


def _format_department_balance_summary(data: dict) -> tuple[str, dict | list | None, dict | None]:
    data, evidence = _extract_evidence(data) if "evidence" in data else (data, None)
    departments = data.get("departments", [])
    leave_type = data.get("leave_type")
    if not departments:
        return "No department balance data found.", data, evidence
    lines = [f"Leave balance summary by department" + (f" ({leave_type})" if leave_type else "") + ":"]
    for d in departments:
        lines.append(
            f"  • {d.get('department','?')}: {d.get('employee_count',0)} employees, "
            f"entitlement {d.get('total_entitlement',0)}, used {d.get('total_used',0)}, remaining {d.get('total_remaining',0)}."
        )
    return "\n".join(lines), data, evidence


def _format_department_summary(data: dict) -> tuple[str, dict | list | None, dict | None]:
    if "message" in data and "departments" not in data:
        return data["message"], None, None

    data, evidence = _extract_evidence(data)
    departments: list[dict] = data.get("departments", [])
    top: list[str] = data.get("top_departments_by_approved_days", [])
    bottom: list[str] = data.get("bottom_departments_by_approved_days", [])

    if not departments:
        answer = "No department data was found for the given filters."
        return answer, data, evidence

    lines = [f"Department leave summary ({len(departments)} department(s)):"] 
    for dept in departments:
        name = dept.get("department", "?")
        total_emp = dept.get("total_employees", 0)
        active = dept.get("active_employees", 0)
        total_req = dept.get("total_requests", 0)
        approved_days = dept.get("approved_days", 0)
        lines.append(
            f"  • {name}: {total_emp} employees ({active} active), "
            f"{total_req} requests, {approved_days} approved days."
        )

    if top:
        top_str = ", ".join(top)
        lines.append(f"\nHighest approved leave: {top_str}.")
    if bottom:
        bottom_str = ", ".join(bottom)
        lines.append(f"Lowest approved leave: {bottom_str}.")

    answer = "\n".join(lines)
    return answer, data, evidence


def _format_document_answer(data: dict) -> tuple[str, dict | list | None, dict | None]:
    # Dispatcher returns a plain dict when no document store is configured.
    if "message" in data and "answer" not in data:
        return data["message"], None, None

    answer = data.get("answer", "").strip()
    if not answer:
        answer = (
            "The available documents do not contain information that answers "
            "this question."
        )

    matched = data.get("matched", False)
    sources: list[dict] = data.get("sources", []) if matched else []

    if sources:
        lines = [answer, "", "Sources:"]
        for source in sources:
            name = source.get("document_name", "document")
            page = source.get("page")
            location = f", page {page}" if page else ""
            lines.append(f"  • {name}{location}")
        answer = "\n".join(lines)

    evidence = {"matched": matched, "sources": sources} if matched else None
    return answer, data, evidence


def _format_clarify(data: dict) -> tuple[str, None, None]:
    if isinstance(data, dict) and data.get("message"):
        return data["message"], None, None
    return (
        "I'm not sure I understood your question. Could you provide more detail? "
        "For example: the employee ID or name, leave type, or date range.",
        None,
        None,
    )


def _format_unsupported(data: dict) -> tuple[str, None, None]:
    return (
        "I can only answer questions about employees, leave requests, leave balances, "
        "leave policies, and department summaries. Could you rephrase your question?",
        None,
        None,
    )
