import logging
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from slowapi.errors import RateLimitExceeded

from routers.health import router as health_router
from routers.issue import router as issue_router
from services import iap_identity, langfuse_config
from services.rate_limiter import handle_rate_limit_exceeded, limiter

load_dotenv()
langfuse_config.configure()

logger = logging.getLogger(__name__)

DEFAULT_STATIC_DIR = Path(__file__).parent / "static"


def create_app(static_dir: Path = DEFAULT_STATIC_DIR) -> FastAPI:
    app = FastAPI()
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
    # Any future router must be included above this line — the static mount
    # matches every remaining path, so routes added after it are unreachable.
    if static_dir.is_dir():
        app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")
    return app


app = create_app()
