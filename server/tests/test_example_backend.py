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
    r = demo.post("/api/face/subjects", data={"external_id": "DEMO", "name": "Demo"},
                  files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 200, r.text
    assert "DEMO" in [s["external_id"] for s in demo.get("/api/face/subjects").json()]

    s = demo.post("/api/face/session", json={"subject_id": "DEMO", "purpose": "demo"}).json()
    assert s["session_token"] and s["mode"] == "verify"
    # The device streams straight to Lumiface with the session token — no key anywhere near it.
    _, body = run_stream(client, s, person_crops[0])
    assert body["ok"], body
    # And the backend reads the verdict for itself.
    done = demo.post("/api/face/done", json={"session_id": s["session_id"]}).json()
    assert done["used"] is True and done["result"]["ok"] is True

    tok = demo.post("/api/face/enrol-token", json={"subject_id": "DEMO2"}).json()["token"]
    assert client.post("/v1/subjects", headers={"Authorization": f"Bearer {tok}"},
                       files={"photo": ("a.jpg", person_crops[0], "image/jpeg")}).status_code == 201
    assert demo.get("/api/face/verifications", params={"subject_id": "DEMO"}).json()
    assert demo.put("/api/face/policy", json={"preset": "balanced"}).json()["preset"] == "balanced"
    assert [p["name"] for p in demo.get("/api/face/policy/presets").json()]
    assert demo.delete("/api/face/subjects/DEMO").status_code == 204
    assert demo.delete("/api/face/subjects/DEMO2").status_code == 204
    # Errors pass through with Lumiface's reason codes.
    r = demo.post("/api/face/done", json={"session_id": "nope"})
    assert r.status_code == 404 and r.json()["detail"]["reason_code"] == "SESSION_NOT_FOUND"
