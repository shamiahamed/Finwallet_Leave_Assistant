import logging
from pathlib import Path
from zipfile import BadZipFile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

from app.exceptions.errors import WorkbookError

logger = logging.getLogger(__name__)


def file_fingerprint(path: Path) -> tuple[int, int] | None:
    # Cheap change signal: nanosecond mtime plus byte size. Returns None when
    # the file is missing so callers can treat that as "cannot refresh".
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_mtime_ns, stat.st_size)


SHEET_EMPLOYEES = "Employees"
SHEET_REQUESTS = "Leave Requests"
SHEET_BALANCES = "Leave Balances"
SHEET_POLICY = "Leave Policy"

REQUIRED_COLUMNS: dict[str, tuple[str, ...]] = {
    SHEET_EMPLOYEES: (
        "Employee ID", "Full Name", "Email", "Department", "Designation",
        "Join Date", "Manager ID", "Office", "Employment Status",
    ),
    SHEET_REQUESTS: (
        "Request ID", "Employee ID", "Leave Type", "Start Date", "End Date",
        "Days", "Approval Status", "Reason", "Approver ID",
    ),
    SHEET_BALANCES: (
        "Employee ID", "Leave Type", "Year", "Annual Entitlement",
        "Approved Days Used", "Remaining Days",
    ),
    SHEET_POLICY: ("Leave Type", "Annual Days", "Accrual", "Payment"),
}
DATE_COLUMNS = {SHEET_EMPLOYEES: ("Join Date",), SHEET_REQUESTS: ("Start Date", "End Date")}
INT_COLUMNS = {
    SHEET_REQUESTS: ("Days",),
    SHEET_BALANCES: ("Year", "Annual Entitlement", "Approved Days Used", "Remaining Days"),
    SHEET_POLICY: ("Annual Days",),
}
# Employees without a manager 
NO_MANAGER_MARKERS = {"—", "–", "-"}
APPROVED_STATUS = "Approved"


class WorkbookRepository:
    """Loads, validates and serves the four workbook sheets."""

    def __init__(self, sheets: dict[str, pd.DataFrame], source_path: Path | None = None, fingerprint: tuple[int, int] | None = None) -> None:
        self._sheets = sheets
        self.source_path = source_path
        self.fingerprint = fingerprint

    # loading
    @classmethod
    def load(cls, path: Path) -> "WorkbookRepository":
        """Read and validate the workbook. Raises WorkbookError with a clear reason."""
        if not path.is_file():
            raise WorkbookError(f"Workbook file not found: {path}")
        try:
            raw = pd.read_excel(path, sheet_name=None, dtype=str, engine="openpyxl")
        except (OSError, ValueError, BadZipFile, InvalidFileException) as exc:
            raise WorkbookError(f"Workbook could not be read as an .xlsx file: {exc}") from exc

        missing = [name for name in REQUIRED_COLUMNS if name not in raw]
        if missing:
            raise WorkbookError(f"Missing worksheet(s): {', '.join(missing)}")

        sheets = {name: cls._normalize_sheet(name, raw[name]) for name in REQUIRED_COLUMNS}
        repo = cls(sheets, source_path=path, fingerprint=file_fingerprint(path))
        repo._check_integrity()
        repo._log_consistency_warnings()
        logger.info("Workbook loaded and validated: %s", repo.row_counts)
        return repo

    @classmethod
    def from_raw_sheets(
        cls,
        raw: dict[str, pd.DataFrame],
        source_path: Path | None = None,
    ) -> "WorkbookRepository":
        """Validate already-read sheets into a repository (used for uploads).

        Reuses the same normalization, integrity, and consistency checks as
        load() so an uploaded file must satisfy the exact known schema before
        it can serve queries.
        """
        missing = [name for name in REQUIRED_COLUMNS if name not in raw]
        if missing:
            raise WorkbookError(f"Missing worksheet(s): {', '.join(missing)}")

        sheets = {name: cls._normalize_sheet(name, raw[name]) for name in REQUIRED_COLUMNS}
        repo = cls(sheets, source_path=source_path)
        repo._check_integrity()
        repo._log_consistency_warnings()
        return repo

    @staticmethod
    def _normalize_sheet(name: str, df: pd.DataFrame) -> pd.DataFrame:
        """Check columns, trim text, reject blanks, and convert date/integer columns."""
        required = REQUIRED_COLUMNS[name]
        absent = [c for c in required if c not in df.columns]
        if absent:
            raise WorkbookError(f"Sheet '{name}' is missing column(s): {', '.join(absent)}")

        df = df[list(required)].copy()
        for col in required:
            df[col] = df[col].str.strip().replace("", pd.NA)

        if name == SHEET_EMPLOYEES:  # blank/dash manager means "no manager", not bad data
            df["Manager ID"] = df["Manager ID"].where(~df["Manager ID"].isin(NO_MANAGER_MARKERS))
        optional = {"Manager ID"} if name == SHEET_EMPLOYEES else set()
        for col in required:
            blanks = int(df[col].isna().sum())
            if blanks and col not in optional:
                raise WorkbookError(f"Sheet '{name}', column '{col}' has {blanks} blank value(s)")

        for col in DATE_COLUMNS.get(name, ()):
            parsed = pd.to_datetime(df[col], format="%Y-%m-%d", errors="coerce")
            if parsed.isna().any():
                raise WorkbookError(f"Sheet '{name}', column '{col}' has non-ISO (YYYY-MM-DD) dates")
            df[col] = parsed

        for col in INT_COLUMNS.get(name, ()):
            parsed = pd.to_numeric(df[col], errors="coerce")
            if parsed.isna().any():
                raise WorkbookError(f"Sheet '{name}', column '{col}' has non-numeric values")
            df[col] = parsed.astype("int64")
        return df.reset_index(drop=True)

    # validation
    def _check_integrity(self) -> None:
        # Hard checks: duplicate keys and broken relationships
        emp, req, bal, pol = (self.employees, self.leave_requests, self.leave_balances, self.leave_policy)
        keys = [
            (SHEET_EMPLOYEES, emp, ["Employee ID"]),
            (SHEET_REQUESTS, req, ["Request ID"]),
            (SHEET_BALANCES, bal, ["Employee ID", "Leave Type"]),
            (SHEET_POLICY, pol, ["Leave Type"]),
        ]
        for sheet, df, cols in keys:
            dupes = int(df.duplicated(cols).sum())
            if dupes:
                raise WorkbookError(f"Sheet '{sheet}' has {dupes} duplicate {'+'.join(cols)} key(s)")

        employee_ids = set(emp["Employee ID"])
        policy_types = set(pol["Leave Type"])

        links = [
            ("Leave Requests.Employee ID", req["Employee ID"], employee_ids),
            ("Leave Requests.Approver ID", req["Approver ID"], employee_ids),
            ("Employees.Manager ID", emp["Manager ID"].dropna(), employee_ids),
            ("Leave Balances.Employee ID", bal["Employee ID"], employee_ids),
            ("Leave Requests.Leave Type", req["Leave Type"], policy_types),
            ("Leave Balances.Leave Type", bal["Leave Type"], policy_types),
        ]

        for label, values, valid in links:
            orphans = sorted(set(values) - valid)
            if orphans:
                raise WorkbookError(f"{label} has unknown reference(s): {', '.join(orphans[:5])}")

        # Requests with end date before start date
        if (req["End Date"] < req["Start Date"]).any():
            raise WorkbookError("Leave Requests contains rows where End Date is before Start Date")

    # Soft checks
    def _log_consistency_warnings(self) -> None:
        req, bal, pol = self.leave_requests, self.leave_balances, self.leave_policy
        span = (req["End Date"] - req["Start Date"]).dt.days + 1
        checks = {
            "requests whose Days differ from the inclusive date span": int((span != req["Days"]).sum()),
            "balances where Remaining != Entitlement - Used": int(
                (bal["Remaining Days"] != bal["Annual Entitlement"] - bal["Approved Days Used"]).sum()
            ),
            "balances whose entitlement differs from the policy sheet": int(
                (bal["Annual Entitlement"] != bal["Leave Type"].map(pol.set_index("Leave Type")["Annual Days"])).sum()
            ),
        }
        approved = (
            req[req["Approval Status"] == APPROVED_STATUS]
            .groupby(["Employee ID", "Leave Type"])["Days"].sum().rename("approved")
        )
        joined = bal.join(approved, on=["Employee ID", "Leave Type"])

        checks["balances whose Used differs from summed approved requests"] = int(
            (joined["Approved Days Used"] != joined["approved"].fillna(0)).sum()
        )
        
        for label, count in checks.items():
            if count:
                logger.warning("Data check: %d %s", count, label)

    # access
    @property
    def employees(self) -> pd.DataFrame:
        return self._sheets[SHEET_EMPLOYEES].copy()

    @property
    def leave_requests(self) -> pd.DataFrame:
        return self._sheets[SHEET_REQUESTS].copy()

    @property
    def leave_balances(self) -> pd.DataFrame:
        return self._sheets[SHEET_BALANCES].copy()

    @property
    def leave_policy(self) -> pd.DataFrame:
        return self._sheets[SHEET_POLICY].copy()

    @property
    def row_counts(self) -> dict[str, int]:
        return {name: len(df) for name, df in self._sheets.items()}
