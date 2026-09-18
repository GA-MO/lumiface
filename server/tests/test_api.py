import json

import pytest

from tests.conftest import HEADERS, make_meta


def test_health(client):
    assert client.get("/health").json() == {"ok": True}


def test_auth_required(client):
    assert client.get("/v1/employees").status_code == 401
    assert client.get("/v1/employees", headers={"X-API-Key": "nope"}).status_code == 401


def test_debug_score_real_face(client, person_crops):
    r = client.post("/v1/debug/score", headers=HEADERS, files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 200, r.text
    face = r.json()[0]
    assert face["spoof_real"] > 0.5
    assert len(face["embedding"]) == 512


@pytest.fixture(scope="module")
def enrolled(client, person_crops):
    r = client.post("/v1/employees", headers=HEADERS, data={"external_id": "E001", "name": "Person A"},
                    files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 201, r.text
    return r.json()


def test_enroll_conflict_and_replace(client, person_crops, enrolled):
    r = client.post("/v1/employees", headers=HEADERS, data={"external_id": "E001"},
                    files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 409
    r = client.post("/v1/employees", headers=HEADERS, data={"external_id": "E001", "replace": "true"},
                    files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 201
    assert [e["external_id"] for e in client.get("/v1/employees", headers=HEADERS).json()] == ["E001"]


def _run_session(client, frame_bytes, employee_id="E001", meta_override=None):
    s = client.post("/v1/sessions", headers=HEADERS, json={"employee_id": employee_id}).json()
    challenges = s["challenges"]
    meta = meta_override(challenges, s["flash_colors"]) if meta_override \
        else make_meta(challenges, flash_colors=s["flash_colors"])
    files = [("frames", (f"{k}.jpg", frame_bytes, "image/jpeg")) for k in s["frame_kinds"]]
    r = client.post(f"/v1/sessions/{s['session_id']}/verify", headers=HEADERS,
                    data={"employee_id": employee_id, "meta": json.dumps(meta)}, files=files)
    return s, r


def test_verify_same_person_ok(client, person_crops, enrolled):
    s, r = _run_session(client, person_crops[0])
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, body
    assert body["reason_code"] == "OK"
    assert body["scores"]["match"] > 0.9
    assert body["scores"]["spoof"] > 0.5
    assert body["checkin_id"]


def test_verify_other_person_rejected(client, person_crops, enrolled):
    _, r = _run_session(client, person_crops[1])
    body = r.json()
    assert body["ok"] is False and body["reason_code"] == "NO_MATCH", body
    assert body["scores"]["match"] < 0.3


def test_verify_too_fast_rejected(client, person_crops, enrolled):
    _, r = _run_session(client, person_crops[0], meta_override=lambda c, f: make_meta(c, step=50, flash_colors=f))
    assert r.json()["reason_code"] == "TIMING_TOO_FAST"


def test_session_has_flash_sequence(client):
    s = client.post("/v1/sessions", headers=HEADERS, json={}).json()
    assert len(s["flash_colors"]) == 3 and len(set(s["flash_colors"])) == 3
    assert s["frame_kinds"] == ["neutral_start", "challenge_0", "challenge_1", "flash_0", "flash_1", "flash_2",
                                "neutral_end"]
    assert s["flash_hold_ms"] > 0


def test_flash_shadow_mode_reports_scores(client, person_crops, enrolled):
    _, r = _run_session(client, person_crops[0])
    body = r.json()
    assert body["ok"] is True, body
    flash = body["details"]["flash"]
    assert flash["enforced"] is False and flash["response"] < 0.5


def test_smile_enforced_rejects_static_face(client, person_crops, enrolled, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "smile_enforce", True)
    _, r = _run_session(client, person_crops[0])
    body = r.json()
    assert body["reason_code"] == "EXPRESSION_MISMATCH", body
    assert body["details"]["smile"]["width_gain"] == 1.0


def test_flash_enforced_rejects_unlit_frames(client, person_crops, enrolled, monkeypatch):
    from app.config import get_settings
    monkeypatch.setattr(get_settings(), "flash_enforce", True)
    _, r = _run_session(client, person_crops[0])
    assert r.json()["reason_code"] == "FLASH_FAIL"


def test_session_single_use(client, person_crops, enrolled):
    s, r = _run_session(client, person_crops[0])
    assert r.status_code == 200
    files = [("frames", (f"{k}.jpg", person_crops[0], "image/jpeg")) for k in s["frame_kinds"]]
    r2 = client.post(f"/v1/sessions/{s['session_id']}/verify", headers=HEADERS,
                     data={"employee_id": "E001",
                           "meta": json.dumps(make_meta(s["challenges"], flash_colors=s["flash_colors"]))},
                     files=files)
    assert r2.status_code == 409


def test_unknown_employee(client, person_crops):
    _, r = _run_session(client, person_crops[0], employee_id="NOPE")
    assert r.status_code == 404


def test_checkins_listed(client, enrolled):
    rows = client.get("/v1/checkins", headers=HEADERS, params={"employee_id": "E001"}).json()
    assert any(r["ok"] for r in rows) and any(r["reason_code"] == "NO_MATCH" for r in rows)
