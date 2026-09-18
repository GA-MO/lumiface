import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import Session, select

from .config import get_settings
from .db import get_engine, init_db
from .models import Project
from .policy import PRESETS, PolicyScopeMiddleware
from .routers import debug, policy, projects, sessions, subjects, verifications
from .services.antispoof import get_antispoof
from .services.face import get_face_engine

log = logging.getLogger("lumiface")


def bootstrap_project() -> None:
    s = get_settings()
    with Session(get_engine()) as db:
        if db.exec(select(Project)).first():
            return
        key = s.bootstrap_api_key or secrets.token_urlsafe(24)
        preset = s.bootstrap_preset if s.bootstrap_preset in PRESETS else "balanced"
        db.add(Project(name=s.bootstrap_project_name, api_key=key, preset=preset))
        db.commit()
        log.warning("created project '%s' (preset %s) with api key: %s", s.bootstrap_project_name, preset, key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bootstrap_project()
    get_face_engine()
    get_antispoof()
    yield


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Lumiface Server", version="0.2.0", lifespan=lifespan)
    app.add_middleware(PolicyScopeMiddleware)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"], expose_headers=["*"])
    app.include_router(projects.router)
    app.include_router(policy.router)
    app.include_router(subjects.router)
    app.include_router(sessions.router)
    app.include_router(verifications.router)
    if s.debug:
        app.include_router(debug.router)

    @app.get("/health")
    def health():
        return {"ok": True, "presets": list(PRESETS)}

    return app


app = create_app()
