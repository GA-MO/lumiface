import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from sqlmodel import Session, select

from .config import get_settings
from .db import get_engine, init_db
from .models import Project
from .routers import checkins, debug, employees, sessions
from .services.antispoof import get_antispoof
from .services.face import get_face_engine

log = logging.getLogger("face_checkin")


def bootstrap_project() -> None:
    s = get_settings()
    with Session(get_engine()) as db:
        if db.exec(select(Project)).first():
            return
        key = s.bootstrap_api_key or secrets.token_urlsafe(24)
        db.add(Project(name=s.bootstrap_project_name, api_key=key))
        db.commit()
        log.warning("created project '%s' with api key: %s", s.bootstrap_project_name, key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bootstrap_project()
    get_face_engine()
    get_antispoof()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Face Check-in Server", version="0.1.0", lifespan=lifespan)
    app.include_router(employees.router)
    app.include_router(sessions.router)
    app.include_router(checkins.router)
    if s.debug:
        app.include_router(debug.router)

    @app.get("/health")
    def health():
        return {"ok": True}

    return app


app = create_app()
