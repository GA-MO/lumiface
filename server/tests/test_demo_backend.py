"""The docs site's demo backend (website/demo-backend) mints liveness sessions for the live demo; drive it against the real app in-process."""
import importlib.util
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app as lumiface_app
from tests.conftest import HEADERS, run_stream

_spec = importlib.util.spec_from_file_location("demo_backend", Path(__file__).resolve().parents[2] / "website/demo-backend/main.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
demo_app = _mod.app


@pytest.fixture(scope="module")
def demo(client):
    demo_app.state.lumiface = httpx.AsyncClient(transport=httpx.ASGITransport(app=lumiface_app), base_url="http://lumiface",
                                                headers={"X-API-Key": HEADERS["X-API-Key"]})
    with TestClient(demo_app) as c:
        yield c


def test_demo_backend_mints_liveness_only_and_reads_the_verdict(client, demo, person_crops):
    assert demo.get("/health").json()["lumiface_up"] is True
    r = demo.post("/demo/session").json()
    assert r["server"] == _mod.LUMIFACE_PUBLIC_URL
    s = r["session"]
    assert s["session_token"] and s["mode"] == "liveness" and s["purpose"] == "website-demo"
    # The browser streams straight to Lumiface with the session token; the demo backend then reads the verdict with the key.
    _, body = run_stream(client, s, person_crops[0])
    assert body["ok"], body
    done = demo.post("/demo/done", json={"session_id": s["session_id"]}).json()
    assert done == {"used": True, "ok": True, "reason_code": "OK"}, "the verdict only: no scores, no details"
    # A session it did not mint is none of its business, even one that exists on the project.
    other = client.post("/v1/sessions", json={"purpose": "elsewhere"}, headers=HEADERS).json()
    r = demo.post("/demo/done", json={"session_id": other["session_id"]})
    assert r.status_code == 404 and r.json()["detail"]["reason_code"] == "SESSION_NOT_FOUND"


def test_demo_rate_limit_is_per_ip_and_per_hour():
    _mod.RECENT.clear()
    rate = _mod.DEMO_RATE
    assert all(_mod.take_slot("1.2.3.4", now=1000.0) for _ in range(rate))
    assert _mod.take_slot("1.2.3.4", now=1000.0) is False, "the address has spent its hour"
    assert _mod.take_slot("5.6.7.8", now=1000.0) is True, "another address has its own"
    assert _mod.take_slot("1.2.3.4", now=1000.0 + _mod.WINDOW_SECONDS + 1) is True, "an hour later the slots are back"


def test_demo_session_answers_429_when_spent(demo, monkeypatch):
    monkeypatch.setattr(_mod, "take_slot", lambda ip, now=None: False)
    r = demo.post("/demo/session")
    assert r.status_code == 429 and r.json()["detail"]["reason_code"] == "DEMO_RATE_LIMITED"
