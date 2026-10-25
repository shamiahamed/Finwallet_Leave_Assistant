
"""Background security and application-health monitoring."""

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

from app.core.config import Settings
from app.services.security_review_service import run_security_review

logger = logging.getLogger(__name__)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


class MonitoringService:
    """Runs periodic security reviews and stores monitoring history."""

    def __init__(
        self,
        settings: Settings,
        history_path: Path,
        interval_seconds: int = 300,
    ) -> None:
        self.settings = settings
        self.history_path = history_path
        self.interval_seconds = max(60, interval_seconds)

        self._lock = Lock()
        self._task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

        self._state = {
            "monitoring_enabled": True,
            "started_at": None,
            "last_scan_at": None,
            "last_scan_status": "not_started",
            "last_scan_error": None,
            "next_scan_in_seconds": self.interval_seconds,
            "current_findings": [],
            "new_findings": [],
            "resolved_findings": [],
            "history": [],
            "events": [],
            "event_counts": {},
        }

        self._load_state()

    def _load_state(self) -> None:
        """Restore the last saved monitoring state after a restart."""
        try:
            if self.history_path.exists():
                saved = json.loads(
                    self.history_path.read_text(encoding="utf-8")
                )
                if isinstance(saved, dict):
                    self._state.update(saved)
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Monitoring history could not be loaded (%s).",
                type(exc).__name__,
            )

    def _save_state_locked(self) -> None:
        """Atomically save state so an interrupted write won't corrupt history."""
        self.history_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.history_path.with_suffix(".tmp")

        try:
            temporary.write_text(
                json.dumps(self._state, indent=2),
                encoding="utf-8",
            )
            os.replace(temporary, self.history_path)
        except OSError:
            logger.exception("Could not persist monitoring state.")
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def snapshot(self) -> dict:
        """Return a detached snapshot suitable for an API response."""
        with self._lock:
            return json.loads(json.dumps(self._state))

    def record_event(
        self,
        event_type: str,
        severity: str = "info",
        message: str = "",
    ) -> None:
        """Record a health/security event without storing secrets or request bodies."""
        event = {
            "id": uuid4().hex,
            "timestamp": utc_now(),
            "type": event_type[:80],
            "severity": severity,
            "message": message[:500],
        }

        with self._lock:
            events = self._state["events"]
            events.append(event)
            self._state["events"] = events[-500:]

            counts = self._state["event_counts"]
            counts[event_type] = counts.get(event_type, 0) + 1

            try:
                self._save_state_locked()
            except OSError:
                # Keep the running application alive if persistence fails.
                logger.exception("Health event could not be saved.")

    async def run_scan(self, document_registry=None) -> dict:
        """Run one security scan and compare it with the previous scan."""
        scan_started = utc_now()

        try:
            review = await asyncio.to_thread(
                run_security_review,
                self.settings,
                document_registry,
            )
            review_data = review.model_dump()

            findings = review_data.get("findings", [])
            previous = self.snapshot().get("current_findings", [])

            previous_by_id = {f["id"]: f for f in previous}
            current_by_id = {f["id"]: f for f in findings}

            new_findings = [
                f for finding_id, f in current_by_id.items()
                if finding_id not in previous_by_id
            ]
            resolved_findings = [
                f for finding_id, f in previous_by_id.items()
                if finding_id not in current_by_id
            ]

            scan = {
                "timestamp": scan_started,
                "status": "ok",
                "summary": review_data.get("summary", {}),
                "checks_run": review_data.get("checks_run", 0),
                "finding_count": len(findings),
            }

            with self._lock:
                self._state.update({
                    "last_scan_at": scan_started,
                    "last_scan_status": "ok",
                    "last_scan_error": None,
                    "current_findings": findings,
                    "new_findings": new_findings,
                    "resolved_findings": resolved_findings,
                })
                self._state["history"].append(scan)
                self._state["history"] = self._state["history"][-200:]

                try:
                    self._save_state_locked()
                except OSError:
                    self._state["last_scan_status"] = "persistence_error"
                    self._state["last_scan_error"] = (
                        "Scan completed, but monitoring history could not be saved."
                    )

            for finding in new_findings:
                self.record_event(
                    "security.finding.new",
                    finding.get("severity", "info"),
                    finding.get("title", "New security finding"),
                )

            for finding in resolved_findings:
                self.record_event(
                    "security.finding.resolved",
                    "info",
                    finding.get("title", "Security finding resolved"),
                )

            logger.info(
                "Security scan completed: %s findings, %s new, %s resolved",
                len(findings),
                len(new_findings),
                len(resolved_findings),
            )
            return self.snapshot()

        except Exception as exc:
            logger.exception("Background security scan failed.")

            with self._lock:
                self._state.update({
                    "last_scan_at": scan_started,
                    "last_scan_status": "failed",
                    "last_scan_error": type(exc).__name__,
                })
                self._state["history"].append({
                    "timestamp": scan_started,
                    "status": "failed",
                    "error": type(exc).__name__,
                })
                self._state["history"] = self._state["history"][-200:]

                try:
                    self._save_state_locked()
                except OSError:
                    logger.exception("Failed scan history could not be saved.")

            self.record_event(
                "monitoring.scan.failed",
                "high",
                "The security scan failed. Check backend logs.",
            )
            return self.snapshot()

    async def start(self, document_registry=None) -> None:
        """Start the periodic scanner once."""
        if self._task and not self._task.done():
            return

        self._stop_event = asyncio.Event()

        with self._lock:
            self._state["started_at"] = utc_now()
            self._state["monitoring_enabled"] = True
            try:
                self._save_state_locked()
            except OSError:
                logger.exception("Could not save monitoring startup state.")

        self._task = asyncio.create_task(
            self._monitor_loop(document_registry),
            name="security-monitor",
        )

    async def _monitor_loop(self, document_registry=None) -> None:
        """Scan immediately, then wait between scans."""
        while self._stop_event and not self._stop_event.is_set():
            await self.run_scan(document_registry)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=self.interval_seconds,
                )
            except asyncio.TimeoutError:
                pass

    async def stop(self) -> None:
        """Stop the scanner cleanly during FastAPI shutdown."""
        if self._stop_event:
            self._stop_event.set()

        if self._task:
            try:
                await asyncio.wait_for(self._task, timeout=10)
            except asyncio.TimeoutError:
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            finally:
                self._task = None

        with self._lock:
            self._state["monitoring_enabled"] = False
            try:
                self._save_state_locked()
            except OSError:
                logger.exception("Could not save monitoring shutdown state.")
