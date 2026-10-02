import json
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import ClassVar

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from routers.health import router as health_router
from routers.issue import router as issue_router
from routers.news_feed import router as news_feed_router
from services import articles_table, iap_identity, issues_db, langfuse_config
from services.rate_limiter import handle_rate_limit_exceeded, limiter

load_dotenv()
langfuse_config.configure()


class JsonLogFormatter(logging.Formatter):
    """Renders log records as one JSON line per entry, so Cloud Run's stdout
    capture parses them into structured (queryable) Cloud Logging fields —
    e.g. jsonPayload.iap_email — instead of one opaque text blob."""

    _RESERVED_KEYS: ClassVar[set[str]] = set(logging.makeLogRecord({}).__dict__.keys())

    def format(self, record: logging.LogRecord) -> str:
        payload = {"severity": record.levelname, "message": record.getMessage()}
        payload.update(
            {k: v for k, v in record.__dict__.items() if k not in self._RESERVED_KEYS}
        )
        return json.dumps(payload)


# Without this, Python's root logger defaults to WARNING and every
# logger.info(...) call in this app is silently dropped before it ever
# reaches stdout/Cloud Logging — confirmed happening in a real deploy
# (see tests/test_logging_config.py).
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JsonLogFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])

logger = logging.getLogger(__name__)

DEFAULT_STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    issues_db.init_schema()
    articles_table.init_schema()
    yield


def create_app(static_dir: Path = DEFAULT_STATIC_DIR) -> FastAPI:
    app = FastAPI(lifespan=lifespan)
    app.state.limiter = limiter
    # Starlette's add_exception_handler is typed for Callable[[Request, Exception], ...];
    # a handler narrowed to a specific exception subclass doesn't satisfy that
    # contravariantly — a known typing limitation, not a bug.
    app.add_exception_handler(RateLimitExceeded, handle_rate_limit_exceeded)  # type: ignore[arg-type]

    @app.middleware("http")
    async def log_iap_identity(request: Request, call_next):
        jwt_assertion = request.headers.get(iap_identity.IAP_JWT_HEADER)
        if jwt_assertion:
            email = iap_identity.verify_iap_identity(jwt_assertion)
            if email:
                logger.info(
                    "Authenticated request",
                    extra={"iap_email": email, "path": request.url.path},
                )
        return await call_next(request)

    app.include_router(health_router)
    app.include_router(issue_router)
    app.include_router(news_feed_router)
    # Any future router must be included above this line — the static mount
    # matches every remaining path, so routes added after it are unreachable.
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
