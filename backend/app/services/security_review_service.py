"""Deterministic, read-only security review.

The review inspects configuration and current runtime state and reports
findings. It never modifies application data, never fixes anything, and never
calls an LLM, so it is safe to run at any time and works even when the LLM
provider is unavailable.

"""

import logging
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

from app.core.config import BACKEND_DIR, Settings

logger = logging.getLogger(__name__)

# Severity ordering used when sorting and summarising findings.
_SEVERITY_RANK = {"high": 3, "medium": 2, "low": 1, "info": 0}

# Known placeholder / example key values that must never be used for real.
_PLACEHOLDER_KEYS = {
    "",
    "changeme",
    "change-me",
    "your-key-here",
    "your_api_key",
    "test",
    "example",
    "none",
    "null",
    "todo",
}

# A Groq-style key prefix helps distinguish a real key from a placeholder.
_GROQ_KEY_PREFIX = "gsk_"


@dataclass
class Finding:
    id: str
    title: str
    severity: str  # "high" | "medium" | "low" | "info"
    category: str  # "configuration" | "secrets" | "input_validation" | "exposure" | "cors"
    evidence: str
    recommendation: str


@dataclass
class SecurityReview:
    status: str
    environment: str
    checks_run: int
    summary: dict[str, int] = field(default_factory=dict)
    findings: list[dict] = field(default_factory=list)

    def model_dump(self) -> dict:
        return asdict(self)


def _env_file_secret_scan(env_path: Path) -> list[Finding]:
    # Detect secrets that appear to be committed to the on-disk .env file
    findings: list[Finding] = []
    if not env_path.exists():
        return findings

    try:
        lines = env_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as exc:  # pragma: no cover - unreadable file is unusual
        logger.warning("Could not read env file for review: %s", type(exc).__name__)
        return findings

    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        lower_key = key.lower()

        is_secret_key = any(
            marker in lower_key for marker in ("api_key", "secret", "token", "password", "passwd")
        )
        if not is_secret_key:
            continue

        if value.lower() in _PLACEHOLDER_KEYS:
            findings.append(
                Finding(
                    id=f"secret.placeholder.{key}",
                    title=f"Secret '{key}' is a placeholder",
                    severity="medium",
                    category="secrets",
                    evidence=f"{key} is set to a placeholder value in {env_path.name}.",
                    recommendation="Set a real value via the environment, or unset it if unused.",
                )
            )
        else:
            findings.append(
                Finding(
                    id=f"secret.committed.{key}",
                    title=f"Secret '{key}' is stored on disk",
                    severity="high",
                    category="secrets",
                    evidence=f"{key} has a non-placeholder value in {env_path.name}.",
                    recommendation=(
                        "Keep secrets out of the repository and .env files; inject them "
                        "through the process environment or a secret manager."
                    ),
                )
            )
    return findings


def _config_findings(settings: Settings, env_file_findings: list[Finding]) -> list[Finding]:
    findings: list[Finding] = list(env_file_findings)

    # Debug/development mode in a non-development build widens the attack surface.
    if settings.app_env.lower() not in {"development", "dev", "test", "local"}:
        pass
    else:
        findings.append(
            Finding(
                id="config.debug_environment",
                title="Application is running in a development environment",
                severity="low",
                category="configuration",
                evidence=f"app_env='{settings.app_env}'.",
                recommendation="Run with a production environment setting when deployed.",
            )
        )

    # Permissive CORS: a wildcard or a large origin list accepts any browser.
    origins = settings.cors_origins
    if any(o == "*" for o in origins):
        findings.append(
            Finding(
                id="cors.wildcard",
                title="CORS allows any origin",
                severity="high",
                category="cors",
                evidence="frontend_origin contains '*'.",
                recommendation="List explicit trusted origins instead of a wildcard.",
            )
        )
    elif len(origins) > 3:
        findings.append(
            Finding(
                id="cors.many_origins",
                title="CORS allows many origins",
                severity="medium",
                category="cors",
                evidence=f"frontend_origin lists {len(origins)} origins.",
                recommendation="Restrict CORS to the origins that genuinely need access.",
            )
        )

    # Insecure (non-HTTPS) origins other than localhost.
    insecure = [
        o for o in origins if o.startswith("http://") and "localhost" not in o and "127.0.0.1" not in o
    ]
    if insecure:
        findings.append(
            Finding(
                id="cors.insecure_origin",
                title="CORS lists a non-HTTPS origin",
                severity="medium",
                category="cors",
                evidence="Insecure origins: " + ", ".join(insecure),
                recommendation="Use https:// origins for anything other than local development.",
            )
        )

    # Upload limits: missing or implausibly large limits enable resource abuse.
    if settings.max_upload_mb <= 0:
        findings.append(
            Finding(
                id="upload.unbounded_size",
                title="Upload size limit is not enforced",
                severity="high",
                category="input_validation",
                evidence=f"max_upload_mb={settings.max_upload_mb}.",
                recommendation="Set a positive max_upload_mb (e.g. 10).",
            )
        )
    elif settings.max_upload_mb > 50:
        findings.append(
            Finding(
                id="upload.large_size_limit",
                title="Upload size limit is large",
                severity="low",
                category="input_validation",
                evidence=f"max_upload_mb={settings.max_upload_mb}.",
                recommendation="Lower the limit unless large uploads are genuinely required.",
            )
        )

    if settings.max_upload_rows <= 0:
        findings.append(
            Finding(
                id="upload.unbounded_rows",
                title="Upload row limit is not enforced",
                severity="high",
                category="input_validation",
                evidence=f"max_upload_rows={settings.max_upload_rows}.",
                recommendation="Set a positive max_upload_rows.",
            )
        )

    if settings.max_upload_columns <= 0:
        findings.append(
            Finding(
                id="upload.unbounded_columns",
                title="Upload column limit is not enforced",
                severity="high",
                category="input_validation",
                evidence=f"max_upload_columns={settings.max_upload_columns}.",
                recommendation="Set a positive max_upload_columns.",
            )
        )

    # The Groq key must be present and well-formed for the LLM features to work.
    key = (settings.groq_api_key or "").strip()
    if not key:
        findings.append(
            Finding(
                id="llm.missing_key",
                title="LLM API key is not configured",
                severity="low",
                category="configuration",
                evidence="groq_api_key is empty.",
                recommendation=(
                    "Set GROQ_API_KEY to enable natural-language questions. "
                    "Structured queries work without it."
                ),
            )
        )
    elif not key.startswith(_GROQ_KEY_PREFIX):
        findings.append(
            Finding(
                id="llm.unexpected_key_format",
                title="LLM API key has an unexpected format",
                severity="info",
                category="configuration",
                evidence="groq_api_key does not start with the expected prefix.",
                recommendation="Confirm the key belongs to the intended provider.",
            )
        )
    return findings


def _document_registry_findings(document_registry) -> list[Finding]:
    """Warn when ingested documents are stored on disk without retention rules."""
    findings: list[Finding] = []
    if document_registry is None:
        return findings
    try:
        documents = document_registry.list_all()
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Security review could not read documents: %s", type(exc).__name__)
        return findings

    if documents:
        findings.append(
            Finding(
                id="documents.stored",
                title="Uploaded documents are persisted in memory/disk",
                severity="info",
                category="exposure",
                evidence=f"{len(documents)} document(s) currently held for retrieval.",
                recommendation=(
                    "Documents are process-local and cleared on restart; avoid uploading "
                    "sensitive material to shared or long-running instances."
                ),
            )
        )
    return findings


def _path_findings(upload_dir: Path) -> list[Finding]:
    """Flag an upload directory that is not writable or does not exist yet."""
    findings: list[Finding] = []
    if upload_dir.exists() and not os.access(upload_dir, os.W_OK):
        findings.append(
            Finding(
                id="storage.upload_dir_not_writable",
                title="Upload directory is not writable",
                severity="medium",
                category="configuration",
                evidence=f"upload_dir='{upload_dir}' is not writable.",
                recommendation="Grant write access or point upload_dir at a writable path.",
            )
        )
    return findings


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen: set[str] = set()
    unique: list[Finding] = []
    for finding in findings:
        if finding.id in seen:
            continue
        seen.add(finding.id)
        unique.append(finding)
    return unique


def run_security_review(settings: Settings, document_registry=None) -> SecurityReview:
    """Run all read-only checks and return a sorted, summarised review."""
    checks = [
        lambda: _config_findings(settings, _env_file_secret_scan(BACKEND_DIR / ".env")),
        lambda: _document_registry_findings(document_registry),
        lambda: _path_findings(settings.upload_dir),
    ]

    findings: list[Finding] = []
    for check in checks:
        try:
            findings.extend(check())
        except Exception as exc:  # pragma: no cover - a check bug must not 500
            logger.warning("Security review check failed: %s", type(exc).__name__)

    findings = _dedupe(findings)
    findings.sort(key=lambda f: (-_SEVERITY_RANK.get(f.severity, 0), f.id))

    summary = {"high": 0, "medium": 0, "low": 0, "info": 0}
    for finding in findings:
        summary[finding.severity] = summary.get(finding.severity, 0) + 1

    return SecurityReview(
        status="ok",
        environment=settings.app_env,
        checks_run=len(checks),
        summary=summary,
        findings=[asdict(f) for f in findings],
    )
