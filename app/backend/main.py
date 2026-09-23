from dotenv import load_dotenv
from fastapi import FastAPI
from slowapi.errors import RateLimitExceeded

from routers.health import router as health_router
from routers.issue import router as issue_router
from services.rate_limiter import handle_rate_limit_exceeded, limiter

load_dotenv()


def create_app() -> FastAPI:
    app = FastAPI()
    app.state.limiter = limiter
    # Starlette's add_exception_handler is typed for Callable[[Request, Exception], ...];
    # a handler narrowed to a specific exception subclass doesn't satisfy that
    # contravariantly — a known typing limitation, not a bug.
    app.add_exception_handler(RateLimitExceeded, handle_rate_limit_exceeded)  # type: ignore[arg-type]
    app.include_router(health_router)
    app.include_router(issue_router)
    return app


app = create_app()
