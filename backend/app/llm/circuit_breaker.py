import logging
import threading
import time
from contextlib import contextmanager
from enum import Enum
from functools import lru_cache

from groq import APIConnectionError, APIStatusError, APITimeoutError

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class CircuitState(str, Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """Raised when the circuit is open and a call must fail fast."""


def is_counted_failure(exc: Exception) -> bool:
    # Timeouts, connection failures, and 5xx responses mean the provider is
    # unhealthy. Rate limits (429), auth errors (401/403), and other 4xx
    # responses prove the provider is reachable, so they must not open it.
    if isinstance(exc, (APITimeoutError, APIConnectionError)):
        return True
    if isinstance(exc, APIStatusError):
        return exc.status_code >= 500
    return False


class CircuitBreaker:
    """Process-local circuit breaker guarding outbound Groq requests.

    CLOSED    - requests pass through and count consecutive transient failures.
    OPEN      - requests fail fast until the cooldown elapses.
    HALF_OPEN - exactly one recovery probe is allowed; other callers fail fast.

    The breaker lives in one Python process, so multiple Uvicorn workers or
    instances each keep their own independent state.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
        clock=time.monotonic,
    ) -> None:
        self._failure_threshold = max(1, int(failure_threshold))
        self._cooldown_seconds = max(0.0, float(cooldown_seconds))
        self._clock = clock
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            return self._state

    def before_request(self) -> None:
        with self._lock:
            if self._state is CircuitState.CLOSED:
                return

            if self._state is CircuitState.OPEN:
                if self._clock() - self._opened_at >= self._cooldown_seconds:
                    self._state = CircuitState.HALF_OPEN
                    logger.warning(
                        "Groq circuit breaker HALF_OPEN; allowing one recovery probe."
                    )
                    return
                logger.debug("Groq circuit breaker OPEN; rejecting request.")
                raise CircuitOpenError(
                    "The LLM provider is temporarily unavailable."
                )

            # HALF_OPEN: a probe is already in flight, so concurrent callers
            # fail fast instead of creating unlimited probes.
            logger.debug("Groq circuit breaker HALF_OPEN; probe already in flight.")
            raise CircuitOpenError("The LLM provider is temporarily unavailable.")

    def record_success(self) -> None:
        with self._lock:
            if self._state is not CircuitState.CLOSED:
                logger.info("Groq circuit breaker CLOSED after successful request.")
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._opened_at = 0.0

    def record_failure(self) -> None:
        with self._lock:
            if self._state is CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                logger.warning("Groq circuit breaker OPEN; recovery probe failed.")
                return

            self._failure_count += 1
            if self._failure_count >= self._failure_threshold:
                self._state = CircuitState.OPEN
                self._opened_at = self._clock()
                logger.warning(
                    "Groq circuit breaker OPEN after %d consecutive failure(s).",
                    self._failure_count,
                )

    @contextmanager
    def guard(self):
        # Every provider call must end in exactly one recorded outcome, so a
        # half-open probe can never get stuck.
        self.before_request()
        try:
            yield
        except Exception as exc:
            if is_counted_failure(exc):
                self.record_failure()
            else:
                # Provider responded (or failed for a non-availability reason).
                self.record_success()
            raise
        else:
            self.record_success()


@lru_cache
def get_circuit_breaker() -> CircuitBreaker:
    settings = get_settings()
    return CircuitBreaker(
        failure_threshold=settings.groq_circuit_failure_threshold,
        cooldown_seconds=settings.groq_circuit_cooldown_seconds,
    )
