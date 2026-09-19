"""The example backend (examples/backend) stands in for a customer backend; drive it against the real app in-process."""
import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app as lumiface_app
from tests.conftest import HEADERS, run_stream

_spec = importlib.util.spec_from_file_location("example_backend", Path(__file__).resolve().parents[2] / "examples/backend/main.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
demo_app = _mod.app


@pytest.fixture(scope="module")
def demo(client):
    # The Lumiface side runs in the same process, reached through an ASGI transport with the project key.
    demo_app.state.lumiface = httpx.AsyncClient(transport=httpx.ASGITransport(app=lumiface_app), base_url="http://lumiface",
                                                headers={"X-API-Key": HEADERS["X-API-Key"]})
    with TestClient(demo_app) as c:
        yield c


def test_example_backend_runs_the_real_loop(client, demo, person_crops):
    assert demo.get("/health").json()["lumiface_up"] is True
    # Registration: the photo lands in the example backend's own user store, not on Lumiface.
    r = demo.post("/api/users", data={"user_id": "DEMO", "name": "Demo"},
                  files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 201, r.text
    assert demo.get("/api/users").json() == [{"id": "DEMO", "name": "Demo"}]

    s = demo.post("/api/face/session", json={"user_id": "DEMO", "purpose": "demo"}).json()
    assert s["session_token"] and s["mode"] == "verify"
    # The device streams straight to Lumiface with the session token — no key anywhere near it.
    _, body = run_stream(client, s, person_crops[0])
    assert body["ok"], body
    # And the backend reads the verdict for itself.
    done = demo.post("/api/face/done", json={"session_id": s["session_id"]}).json()
    assert done["used"] is True and done["result"]["ok"] is True and done["reference"] is True
    assert done["user_id"] == "DEMO" and done["verified"] is True, "the backend's own session → user record decides"

    assert demo.post("/api/face/session", json={"user_id": "NOBODY"}).status_code == 404
    s = demo.post("/api/face/session", json={"purpose": "kiosk"}).json()
    assert s["mode"] == "liveness"
    _, body = run_stream(client, s, person_crops[1])
    assert body["ok"] is True
    done = demo.post("/api/face/done", json={"session_id": s["session_id"]}).json()
    assert done["user_id"] is None and done["verified"] is False, "liveness proves a person, not a user"
    assert demo.get("/api/face/verifications", params={"purpose": "demo"}).json()
    assert demo.delete("/api/users/DEMO").status_code == 204 and demo.get("/api/users").json() == []
    assert demo.put("/api/face/policy", json={"preset": "balanced"}).json()["preset"] == "balanced"
    assert [p["name"] for p in demo.get("/api/face/policy/presets").json()]
    # Errors pass through with Lumiface's reason codes.
    r = demo.post("/api/face/done", json={"session_id": "nope"})
    assert r.status_code == 404 and r.json()["detail"]["reason_code"] == "SESSION_NOT_FOUND"
