from dotenv import load_dotenv
from fastapi import FastAPI

from routers.health import router as health_router

load_dotenv()


def create_app() -> FastAPI:
    app = FastAPI()
    app.include_router(health_router)
    return app


app = create_app()
