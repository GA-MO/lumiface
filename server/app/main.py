import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlmodel import Session, select

from .config import get_settings
from .db import get_engine, init_db
from .deps import new_api_key
from .models import Project
from .policy import PRESETS, PolicyScopeMiddleware
from .routers import debug, policy, projects, sessions, subjects, verifications
from .services.antispoof import get_antispoof
from .services.face import get_face_engine
from .services.retention import retention_loop

log = logging.getLogger("lumiface")


def bootstrap_project() -> None:
    s = get_settings()
    with Session(get_engine()) as db:
        if db.exec(select(Project)).first():
            return
        key = s.bootstrap_api_key or new_api_key()
        preset = s.bootstrap_preset if s.bootstrap_preset in PRESETS else "balanced"
        db.add(Project(name=s.bootstrap_project_name, api_key=key, preset=preset))
        db.commit()
        if s.bootstrap_api_key:
            log.warning("created project '%s' (preset %s) with the api key from BOOTSTRAP_API_KEY",
                        s.bootstrap_project_name, preset)
        else:
            # Shown once; an operator-supplied key is never echoed into the logs.
            log.warning("created project '%s' (preset %s) with generated api key: %s", s.bootstrap_project_name,
                        preset, key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    bootstrap_project()
    get_face_engine()
    get_antispoof()
    purger = asyncio.create_task(retention_loop()) if get_settings().retention_interval_seconds > 0 else None
    yield
    if purger:
        purger.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await purger


class BodyLimitMiddleware:
    """Rejects oversized uploads before the multipart parser sees them (FastAPI parses forms before auth)."""

    def __init__(self, app, limit: int) -> None:
        self.app = app
        self.limit = limit

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            length = next((v for k, v in scope["headers"] if k == b"content-length"), None)
            if length and length.isdigit() and int(length) > self.limit:
                response = JSONResponse({"detail": {"reason_code": "PAYLOAD_TOO_LARGE"}}, status_code=413)
                await response(scope, receive, send)
                return
        await self.app(scope, receive, send)


def create_app() -> FastAPI:
    s = get_settings()
    app = FastAPI(title="Lumiface Server", version="0.2.0", lifespan=lifespan)
    app.add_middleware(PolicyScopeMiddleware)
    app.add_middleware(BodyLimitMiddleware, limit=s.max_upload_bytes)
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
