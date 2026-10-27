
from app.exceptions.errors import InvalidFilterError
from app.schemas.intent import QueryIntent
from app.services.employee_service import EmployeeService
from app.services.leave_request_service import LeaveRequestService
from app.services.balance_service import BalanceService
from app.services.policy_service import PolicyService
from app.services.department_service import DepartmentService


def _resolve_employee_id(
    intent: QueryIntent,
    employees: EmployeeService,
) -> str | None:
    # An explicit employee ID takes priority over a name.
    if intent.employee_id:
        return intent.employee_id

    if intent.employee_name:
        return employees.find_by_name(
            intent.employee_name
        ).employee.employee_id

    return None


def dispatch_query(
    intent: QueryIntent,
    employees: EmployeeService,
    requests: LeaveRequestService,
    balances: BalanceService,
    policies: PolicyService,
    departments: DepartmentService,
    *,
    question: str = "",
    documents=None,
    settings=None,
    document_names: list[str] | None = None,
    limit: int | None = None,
):
    # Employee list
    if intent.intent == "employee_list":
        if intent.department:
            valid_depts = set(
                employees._repo.employees["Department"]
                .dropna()
                .astype(str)
                .unique()
                .tolist()
            )
            if intent.department not in valid_depts:
                raise InvalidFilterError(
                    f"I couldn't find department '{intent.department}'. "
                    f"Please check the department name."
                )
        return employees.list_employees(
            department=intent.department,
            employment_status=intent.employment_status,
        )

    # Help/capabilities
    if intent.intent == "help":
        return {
            "message": (
                "I can help with:\n"
                "  - Employee lookups, employee lists, and headcounts by "
                "department or status.\n"
                "  - Leave balances, including balances by employee, department, "
                "or leave type.\n"
                "  - Leave requests and leave history, filtered by employee, "
                "department, status, leave type, or date range.\n"
                "  - Leave policies and department-level leave summaries.\n"
                "  - Questions about uploaded policy documents.\n\n"
                "Try: \"Show employees in Finance\", \"What is EMP001's leave "
                "balance?\", \"Show pending leave requests\", or \"What is the "
                "Sick Leave policy?\""
            )
        }

    # Employee lookup
    if intent.intent == "employee_lookup":
        if intent.employee_id:
            return employees.get_employee(intent.employee_id)

        if intent.employee_name:
            return employees.find_by_name(intent.employee_name)

        return {
            "message": "Please provide an employee ID or name to look up."
        }

    # Employee headcount
    if intent.intent == "employee_headcount":
        return employees.headcount(
            department=intent.department,
            employment_status=intent.employment_status,
        )

    # Leave requests
    if intent.intent == "leave_requests":
        employee_id = _resolve_employee_id(intent, employees)

        return requests.list_requests(
            employee_id=employee_id,
            leave_type=intent.leave_type,
            approval_status=intent.approval_status,
            start_date=intent.start_date,
            end_date=intent.end_date,
            department=intent.department,
            limit=limit or 50,
            date_mode=intent.date_mode,
        )

    # Department balance summary
    if intent.intent == "department_balance_summary":
        return balances.get_department_balance_summary(
            leave_type=intent.leave_type,
        )

    # Leave balance
    if intent.intent == "leave_balance":
        if intent.scope == "all":
            return balances.get_all_balances(
                leave_type=intent.leave_type,
            )

        if intent.scope == "department":
            if not intent.department:
                return {
                    "message": (
                        "Please specify the department whose "
                        "leave balances you want to see."
                    )
                }

            return balances.get_department_balances(
                department=intent.department,
                leave_type=intent.leave_type,
            )

        # Default: one employee
        employee_id = _resolve_employee_id(intent, employees)

        if not employee_id:
            return {
                "message": (
                    "Please provide an employee ID to check "
                    "a leave balance."
                )
            }

        return balances.get_balances(
            employee_id=employee_id,
            leave_type=intent.leave_type,
        )

    # Leave policy
    if intent.intent == "leave_policy":
        return policies.get_policies(intent.leave_type)

    # Department leave activity summary
    if intent.intent == "department_summary":
        return departments.summary(
            department=intent.department,
            leave_type=intent.leave_type,
            start_date=intent.start_date,
            end_date=intent.end_date,
        )

    # Questions answered from uploaded documents
    if intent.intent == "document_question":
        if documents is None or settings is None:
            return {
                "message": (
                    "Document questions are not available because "
                    "no document store is configured."
                )
            }

        from app.services.rag_service import answer_document_question

        return answer_document_question(
            question,
            documents,
            settings,
            document_name=getattr(intent, "document_name", None),
            document_names=document_names,
        )

    # Clarification
    if intent.intent == "clarify":
        return {
            "message": (
                "Could you clarify your question? Please include "
                "the employee ID, leave type, or date range if relevant."
            )
        }

    # Unsupported questions
    if intent.intent == "unsupported":
        if (
            documents is not None
            and settings is not None
            and not documents.is_empty()
        ):
            from app.services.rag_service import answer_document_question
            return answer_document_question(
                question,
                documents,
                settings,
                document_name=getattr(intent, "document_name", None),
            )

        return {
            "message": (
                "I can answer questions about employees, leave requests, "
                "leave balances, leave policies, and department summaries. "
                "Upload a policy document if your question is about "
                "written policy."
            )
        }

    return {
        "message": (
            f"The intent '{intent.intent}' has not been implemented yet."
        )
    }
