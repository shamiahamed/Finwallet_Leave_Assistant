from app.repositories.workbook_repository import SHEET_POLICY, WorkbookRepository
from app.schemas.common import Evidence
from app.schemas.leave import PolicyOut, PolicyResponse
from app.utils.choices import resolve_choice


class PolicyService:
    def __init__(self, repository: WorkbookRepository) -> None:
        self._repo = repository

    def get_policies(self, leave_type: str | None = None) -> PolicyResponse:
        df = self._repo.leave_policy

        # Filter by one or more leave types.
        if leave_type:
            leave_types = [item.strip() for item in leave_type.split(",")]

            valid_types = [
                resolve_choice(item, df["Leave Type"], "leave type")
                for item in leave_types
            ]

            df = df[df["Leave Type"].isin(valid_types)]

        # Build the policy response.
        return PolicyResponse(
            policies=[
                PolicyOut(
                    leave_type=r["Leave Type"],
                    annual_days=int(r["Annual Days"]),
                    accrual=r["Accrual"],
                    payment=r["Payment"],
                )
                for _, r in df.iterrows()
            ],
            evidence=Evidence(worksheets=[SHEET_POLICY]),
        )