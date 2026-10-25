# Logging setup. Log messages must never contain secrets or full employee records.
import logging
from contextvars import ContextVar

# Correlation ID for the in-flight request. Set by the request middleware and
# read by the log filter so every line from a request shares one ID.
request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=level.upper(),
        format="%(asctime)s | %(levelname)-7s | %(request_id)s | %(name)s | %(message)s",
        force=True,
    )
    # Attach the filter to the root handlers so every record gets a request ID.
    flt = _RequestIdFilter()
    for handler in logging.getLogger().handlers:
        handler.addFilter(flt)
    # Request logging is done by middleware
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
