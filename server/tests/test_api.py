import json

import pytest

from tests.conftest import ADMIN, HEADERS, run_stream


def test_health(client):
    body = client.get("/health").json()
    assert body["ok"] is True and "strict" in body["presets"]


def test_auth_required(client):
    assert client.get("/v1/subjects").status_code == 401
    assert client.get("/v1/subjects", headers={"X-API-Key": "nope"}).status_code == 401


def test_debug_score_real_face(client, person_crops):
    r = client.post("/v1/debug/score", headers=HEADERS, files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 200, r.text
    face = r.json()[0]
    assert face["spoof_real"] > 0.5
    assert len(face["embedding"]) == 512


@pytest.fixture(scope="module")
def enrolled(client, person_crops):
    r = client.post("/v1/subjects", headers=HEADERS, data={"external_id": "E001", "name": "Person A"},
                    files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 201, r.text
    return r.json()


def test_enroll_conflict_and_replace(client, person_crops, enrolled):
    r = client.post("/v1/subjects", headers=HEADERS, data={"external_id": "E001"},
                    files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 409
    r = client.post("/v1/subjects", headers=HEADERS, data={"external_id": "E001", "replace": "true"},
                    files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 201
    assert [e["external_id"] for e in client.get("/v1/subjects", headers=HEADERS).json()] == ["E001"]
    assert client.get("/v1/subjects/E001", headers=HEADERS).json()["name"] == "Person A"


def _run_session(client, frame_bytes, subject_id="E001", purpose="", headers=HEADERS, **kw):
    """Backend creates the session; the device streams it. Returns (session, plan, result message)."""
    sess = client.post("/v1/sessions", headers=headers, json={"subject_id": subject_id, "purpose": purpose}).json()
    plan, result = run_stream(client, sess, frame_bytes, **kw)
    return sess, plan, result


def test_verify_same_person_ok(client, person_crops, enrolled):
    s, plan, body = _run_session(client, person_crops[0], purpose="checkin")
    assert "challenges" not in s and "flash_colors" not in s, "the plan only travels over the stream"
    assert plan["challenges"] == ["smile"] and len(plan["flash_colors"]) == 3 and plan["client_config"]["align_hold_ms"]
    assert body["type"] == "result" and body["ok"] is True, body
    assert body["mode"] == "verify" and body["reason_code"] == "OK"
    assert body["scores"]["match"] > 0.9 and body["scores"]["spoof"] > 0.5
    assert body["verification_id"] and body["details"] == {}, "no per-frame scores for the device"


def test_verify_other_person_rejected(client, person_crops, enrolled):
    _, _, body = _run_session(client, person_crops[1])
    assert body["ok"] is False and body["reason_code"] == "NO_MATCH", body
    assert body["scores"]["match"] < 0.3


def test_liveness_only_session_needs_no_subject(client, person_crops):
    s, _, body = _run_session(client, person_crops[1], subject_id=None, purpose="kiosk")
    assert s["mode"] == "liveness"
    assert body["ok"] is True and body["mode"] == "liveness", body
    assert body["scores"]["match"] is None and body["scores"]["consistency"] > 0.9


def test_too_fast_on_the_server_clock(client, person_crops, enrolled):
    # The device's own timestamps are ignored: the server measures the session on its clock.
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"min_session_ms": 1500}})
    try:
        _, _, body = _run_session(client, person_crops[0])
        assert body["reason_code"] == "TIMING_TOO_FAST", body
        _, _, body = _run_session(client, person_crops[0], pause=1.6)
        assert body["ok"] is True, body
    finally:
        client.delete("/v1/policy", headers=HEADERS)


def test_events_out_of_order_are_rejected(client, person_crops, enrolled):
    _, _, body = _run_session(client, person_crops[0], order=["challenge_done:0", "aligned", "frames"])
    assert body["reason_code"] == "TIMING_ORDER"
    _, _, body = _run_session(client, person_crops[0], order=["aligned", "frames"])  # never finished the plan
    assert body["reason_code"] == "TIMING_ORDER"


def test_frozen_feed_is_rejected(client, person_crops, enrolled):
    sess = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    with client.websocket_connect(f"/v1/sessions/{sess['session_id']}/stream") as ws:
        ws.send_json({"type": "hello", "token": sess["session_token"]})
        plan = ws.receive_json()
        same = (0).to_bytes(8, "big") + person_crops[0]
        for _ in range(4):
            ws.send_bytes(same)
        ws.send_json({"type": "event", "name": "aligned"})
        for i in range(len(plan["challenges"])):
            ws.send_bytes(same)
            ws.send_bytes(same)
            ws.send_json({"type": "event", "name": "challenge_done", "index": i})
        for i in range(len(plan["flash_colors"])):
            ws.send_json({"type": "event", "name": "flash", "index": i})
            ws.send_bytes(same)
        ws.send_json({"type": "event", "name": "flash_end"})
        ws.send_bytes(same)
        ws.send_bytes(same)
        ws.send_json({"type": "end"})
        assert ws.receive_json()["reason_code"] == "FRAMES_STATIC"


def test_session_carries_client_config_only(client):
    s = client.post("/v1/sessions", headers=HEADERS, json={}).json()
    assert set(s) == {"session_id", "session_token", "mode", "purpose", "expires_at", "ttl_seconds", "client_config"}
    assert s["client_config"]["parallax_min_shift"] == 0.08
    assert s["client_config"]["blink_max_ms"] == 600


def _details(client, session_id):
    from sqlmodel import Session, select

    from app.db import get_engine
    from app.models import Verification

    with Session(get_engine()) as db:
        row = db.exec(select(Verification).where(Verification.session_id == session_id)).one()
        return json.loads(row.details)


def test_flash_shadow_mode_reports_scores(client, person_crops, enrolled):
    s, _, body = _run_session(client, person_crops[0])
    assert body["ok"] is True, body
    d = _details(client, s["session_id"])
    assert d["flash"]["enforced"] is False and d["flash"]["response"] < 0.5
    assert [e["name"] for e in d["events"]] == ["aligned", "challenge_done", "flash", "flash", "flash", "flash_end", "end"]
    assert d["client"] == {"platform": "test", "user_agent": "testclient"} and d["frames"] >= 8


def test_smile_enforced_rejects_static_face(client, person_crops, enrolled):
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"smile_enforce": True}})
    try:
        s, _, body = _run_session(client, person_crops[0])
        assert body["reason_code"] == "EXPRESSION_MISMATCH", body
        assert _details(client, s["session_id"])["challenge_0"]["width_gain"] == 1.0
    finally:
        client.delete("/v1/policy", headers=HEADERS)


def test_flash_enforced_rejects_unlit_frames(client, person_crops, enrolled):
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"flash_enforce": True}})
    try:
        _, _, body = _run_session(client, person_crops[0])
        assert body["reason_code"] == "FLASH_FAIL"
    finally:
        client.delete("/v1/policy", headers=HEADERS)


def test_session_single_use(client, person_crops, enrolled):
    s, _, body = _run_session(client, person_crops[0])
    assert body["ok"] is True
    again, _ = run_stream(client, s, person_crops[0])
    assert again == {"type": "error", "reason_code": "SESSION_USED"}


def test_unknown_subject(client, person_crops):
    _, plan, _ = _run_session(client, person_crops[0], subject_id="NOPE")
    assert plan == {"type": "error", "reason_code": "SUBJECT_NOT_FOUND"}


def test_verifications_listed_and_filtered(client, enrolled):
    rows = client.get("/v1/verifications", headers=HEADERS, params={"subject_id": "E001"}).json()
    assert any(r["ok"] for r in rows) and any(r["reason_code"] == "NO_MATCH" for r in rows)
    kiosk = client.get("/v1/verifications", headers=HEADERS, params={"purpose": "kiosk"}).json()
    assert kiosk and all(r["purpose"] == "kiosk" and r["subject_id"] is None for r in kiosk)


def test_policy_defaults_follow_environment(client):
    body = client.get("/v1/policy", headers=HEADERS).json()
    assert body["preset"] == "balanced" and body["overrides"] == {}
    assert body["effective"]["challenge_pool"] == "smile"
    assert body["effective"]["min_face_size"] == 60
    assert body["effective"]["client"]["blink_min_ms"] == 40


def test_policy_presets_listed_with_schema(client):
    presets = {p["name"]: p for p in client.get("/v1/policy/presets", headers=HEADERS).json()}
    assert set(presets) == {"balanced", "strict", "relaxed", "emulator"}
    assert presets["strict"]["effective"]["challenge_count"] == 3
    assert presets["emulator"]["effective"]["flash_enforce"] is False
    schema = client.get("/v1/policy/schema", headers=HEADERS).json()
    names = {f["name"] for f in schema}
    assert {"match_threshold", "client.parallax_min_shift"} <= names
    assert all(f["description"] for f in schema)


def test_policy_update_rejects_unknown_field(client):
    r = client.put("/v1/policy", headers=HEADERS, json={"overrides": {"no_such_field": 1}})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "POLICY_INVALID"
    r = client.put("/v1/policy", headers=HEADERS, json={"preset": "paranoid"})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "UNKNOWN_PRESET"


def test_strict_preset_rejects_the_same_person_at_higher_bar(client, person_crops, enrolled):
    r = client.put("/v1/policy", headers=HEADERS,
                   json={"preset": "strict", "overrides": {"spoof_threshold": 0.999, "challenge_count": 2}})
    assert r.status_code == 200, r.text
    assert r.json()["effective"]["turn_strict_direction"] is True
    try:
        s, _, body = _run_session(client, person_crops[0])
        assert s["client_config"]["parallax_min_shift"] == 0.10
        assert body["reason_code"] == "SPOOF"
    finally:
        client.delete("/v1/policy", headers=HEADERS)
    assert client.get("/v1/policy", headers=HEADERS).json()["preset"] == "balanced"


def test_admin_creates_project_with_its_own_policy(client, person_crops):
    assert client.post("/v1/projects", json={"name": "x"}).status_code == 401
    r = client.post("/v1/projects", headers=ADMIN, json={"name": "kiosk-app", "preset": "emulator"})
    assert r.status_code == 201, r.text
    created = r.json()
    key = created["api_key"]
    assert key and created["preset"] == "emulator"
    tenant = {"X-API-Key": key}
    s = client.post("/v1/sessions", headers=tenant, json={}).json()
    assert s["client_config"]["min_face_width_fraction"] == 0.2
    assert client.get("/v1/policy", headers=tenant).json()["effective"]["flash_enforce"] is False
    assert client.get("/v1/subjects", headers=tenant).json() == []
    assert client.post("/v1/projects", headers=ADMIN, json={"name": "kiosk-app"}).status_code == 409
    listed = {p["name"]: p for p in client.get("/v1/projects", headers=ADMIN).json()}
    assert listed["kiosk-app"]["api_key"] is None and listed["default"]["subjects"] == 1
    rotated = client.post(f"/v1/projects/{created['id']}/rotate-key", headers=ADMIN).json()["api_key"]
    assert rotated != key
    assert client.get("/v1/subjects", headers=tenant).status_code == 401
    assert client.delete(f"/v1/projects/{created['id']}", headers=ADMIN).status_code == 204


def _enrol(client, crop, external_id, **data):
    return client.post("/v1/subjects", headers=HEADERS, data={"external_id": external_id, **data},
                       files={"photo": ("a.jpg", crop, "image/jpeg")})


def test_subject_ttl_expires_and_purges(client, person_crops):
    from datetime import timedelta

    from sqlmodel import Session, select

    from app.db import get_engine
    from app.models import Subject, Verification, VerifySession, utcnow
    from app.services.retention import purge

    assert _enrol(client, person_crops[0], "TMP", ttl_seconds="-1").status_code == 422
    r = _enrol(client, person_crops[0], "TMP", ttl_seconds="3600")
    assert r.status_code == 201, r.text
    assert r.json()["expires_at"] is not None
    _, _, body = _run_session(client, person_crops[0], subject_id="TMP")
    assert body["ok"], body
    assert client.get("/v1/subjects/E001", headers=HEADERS).json()["expires_at"] is None  # policy default 0 keeps

    # Back-date the expiry: the subject vanishes from the API before the purge runs.
    with Session(get_engine()) as db:
        row = db.exec(select(Subject).where(Subject.external_id == "TMP")).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.add(row)
        db.commit()
    assert client.get("/v1/subjects/TMP", headers=HEADERS).status_code == 404
    assert "TMP" not in [s["external_id"] for s in client.get("/v1/subjects", headers=HEADERS).json()]
    _, plan, _ = _run_session(client, person_crops[0], subject_id="TMP")
    assert plan["reason_code"] == "SUBJECT_NOT_FOUND"
    # Re-enrolling an expired id needs no replace flag.
    assert _enrol(client, person_crops[0], "TMP").status_code == 201
    assert client.get("/v1/subjects/TMP", headers=HEADERS).json()["expires_at"] is None

    with Session(get_engine()) as db:
        row = db.exec(select(Subject).where(Subject.external_id == "TMP")).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.add(row)
        db.commit()
        before = len(db.exec(select(VerifySession)).all())
        counts = purge(db, now=utcnow() + timedelta(days=1))
        assert counts["subjects"] == 1 and counts["sessions"] == before
        assert db.exec(select(Subject).where(Subject.external_id == "TMP")).first() is None
        assert db.exec(select(Subject).where(Subject.external_id == "E001")).first() is not None
        # The audit log survives without the link to the deleted embedding.
        logged = db.exec(select(Verification).where(Verification.subject_external_id == "TMP")).all()
        assert logged and all(v.subject_id is None for v in logged)
    assert client.get("/v1/verifications", headers=HEADERS, params={"subject_id": "TMP"}).json()


def test_subject_ttl_from_policy(client, person_crops):
    r = client.put("/v1/policy", headers=HEADERS, json={"overrides": {"subject_ttl_seconds": 60}, "merge": True})
    assert r.status_code == 200, r.text
    assert r.json()["effective"]["subject_ttl_seconds"] == 60
    try:
        r = _enrol(client, person_crops[0], "POL")
        assert r.status_code == 201 and r.json()["expires_at"] is not None
        r = _enrol(client, person_crops[0], "POL2", ttl_seconds="0")
        assert r.status_code == 201 and r.json()["expires_at"] is None
    finally:
        client.put("/v1/policy", headers=HEADERS, json={"overrides": {"subject_ttl_seconds": 0}, "merge": True})
        client.delete("/v1/subjects/POL", headers=HEADERS)
        client.delete("/v1/subjects/POL2", headers=HEADERS)


def test_session_token_is_the_only_way_in(client, person_crops, enrolled):
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    assert s["session_token"]
    # Wrong or missing token: the session does not exist for this caller, and nothing is spent.
    assert run_stream(client, s, person_crops[0], token="nope")[0] == {"type": "error", "reason_code": "SESSION_NOT_FOUND"}
    assert run_stream(client, s, person_crops[0], token="")[0]["reason_code"] == "SESSION_NOT_FOUND"
    with client.websocket_connect(f"/v1/sessions/{s['session_id']}/stream") as ws:
        ws.send_json({"type": "nope"})
        assert ws.receive_json()["reason_code"] == "HELLO_INVALID"
    # The right token, and only for that one session.
    s2 = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    assert run_stream(client, s2, person_crops[0], token=s["session_token"])[0]["reason_code"] == "SESSION_NOT_FOUND"
    _, body = run_stream(client, s, person_crops[0])
    assert body["ok"] is True, body
    assert client.get(f"/v1/sessions/{s['session_id']}", headers=HEADERS).json()["used"] is True


def test_enrol_token_flow(client, person_crops):
    r = client.post("/v1/subjects/tokens", headers=HEADERS,
                    json={"external_id": "TOK", "name": "Via token", "ttl_seconds": 0})
    assert r.status_code == 201, r.text
    tok = r.json()["token"]
    bearer = {"Authorization": f"Bearer {tok}"}
    photo = {"photo": ("a.jpg", person_crops[0], "image/jpeg")}
    # The device cannot pick another subject than the one the backend fixed.
    r = client.post("/v1/subjects", headers=bearer, data={"external_id": "OTHER"}, files=photo)
    assert r.status_code == 403 and r.json()["detail"]["reason_code"] == "ENROL_TOKEN_MISMATCH"
    r = client.post("/v1/subjects", headers=bearer, files=photo)
    assert r.status_code == 201, r.text
    assert r.json() == {**r.json(), "external_id": "TOK", "name": "Via token", "expires_at": None}
    # Single use.
    r = client.post("/v1/subjects", headers=bearer, files=photo)
    assert r.status_code == 401 and r.json()["detail"]["reason_code"] == "ENROL_TOKEN_INVALID"
    assert client.post("/v1/subjects", headers={"Authorization": "Bearer nope"}, files=photo).status_code == 401
    # The project key still needs external_id, and the token cannot manage subjects.
    r = client.post("/v1/subjects", headers=HEADERS, files=photo)
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "EXTERNAL_ID_REQUIRED"
    assert client.get("/v1/subjects", headers=bearer).status_code == 401
    assert client.delete("/v1/subjects/TOK", headers=bearer).status_code == 401
    assert client.delete("/v1/subjects/TOK", headers=HEADERS).status_code == 204


def test_device_cannot_pick_the_subject(client, person_crops, enrolled):
    # The subject is fixed by the backend at creation; the stream has no field to name one, and a
    # liveness session stays liveness whatever the device streams.
    s = client.post("/v1/sessions", headers=HEADERS, json={}).json()
    _, body = run_stream(client, s, person_crops[1])
    assert body["ok"] is True and body["mode"] == "liveness" and body["scores"]["match"] is None
    rows = client.get("/v1/verifications", headers=HEADERS, params={"session_id": s["session_id"]}).json()
    assert rows[0]["subject_id"] is None


def test_backend_reads_session_outcome(client, person_crops, enrolled):
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001", "purpose": "login"}).json()
    bearer = {"Authorization": f"Bearer {s['session_token']}"}
    assert client.get(f"/v1/sessions/{s['session_id']}", headers=bearer).status_code == 401
    before = client.get(f"/v1/sessions/{s['session_id']}", headers=HEADERS).json()
    assert before["used"] is False and before["result"] is None and before["subject_id"] == "E001"
    _, body = run_stream(client, s, person_crops[0])
    assert body["ok"] is True
    after = client.get(f"/v1/sessions/{s['session_id']}", headers=HEADERS).json()
    assert after["used"] is True and after["result"]["ok"] is True
    assert after["result"]["verification_id"] == body["verification_id"]
    rows = client.get("/v1/verifications", headers=HEADERS, params={"session_id": s["session_id"]}).json()
    assert [v["id"] for v in rows] == [body["verification_id"]]
    # Another project cannot read it.
    other = client.post("/v1/projects", headers=ADMIN, json={"name": "other-tenant"}).json()
    try:
        assert client.get(f"/v1/sessions/{s['session_id']}", headers={"X-API-Key": other["api_key"]}).status_code == 404
    finally:
        client.delete(f"/v1/projects/{other['id']}", headers=ADMIN)


def test_bad_uploads_are_answered_not_crashed(client, person_crops, enrolled):
    # Undecodable frames simply show no face.
    _, _, body = _run_session(client, b"not a jpeg at all")
    assert body["type"] == "result" and body["reason_code"] == "NO_FACE"
    # An oversized frame ends the stream.
    from app.config import get_settings

    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    with client.websocket_connect(f"/v1/sessions/{s['session_id']}/stream") as ws:
        ws.send_json({"type": "hello", "token": s["session_token"]})
        assert ws.receive_json()["type"] == "plan"
        ws.send_bytes((0).to_bytes(8, "big") + b"x" * (get_settings().max_frame_bytes + 1))
        assert ws.receive_json()["reason_code"] == "PAYLOAD_TOO_LARGE"
    # Garbage where an event should be.
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    with client.websocket_connect(f"/v1/sessions/{s['session_id']}/stream") as ws:
        ws.send_json({"type": "hello", "token": s["session_token"]})
        ws.receive_json()
        ws.send_text("{not json")
        assert ws.receive_json()["reason_code"] == "EVENT_INVALID"
    # Non-ASCII tokens never 500.
    from fastapi import HTTPException

    from app.deps import bearer_token, token_matches

    with pytest.raises(HTTPException) as e:
        bearer_token("Bearer é")
    assert e.value.status_code == 401
    assert token_matches("é", "abc") is False and bearer_token("Basic dXNlcjpwYXNz") is None


def test_enrol_token_cannot_replace_and_is_returned_on_failure(client, person_crops, enrolled):
    assert client.post("/v1/subjects/tokens", headers=HEADERS,
                       json={"external_id": "E001", "replace": True}).status_code == 201  # ignored, not honoured
    tok = client.post("/v1/subjects/tokens", headers=HEADERS, json={"external_id": "E001"}).json()["token"]
    bearer = {"Authorization": f"Bearer {tok}"}
    r = client.post("/v1/subjects", headers=bearer, data={"replace": "true"},
                    files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 403
    r = client.post("/v1/subjects", headers=bearer, files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 409 and r.json()["detail"]["reason_code"] == "SUBJECT_EXISTS"
    assert client.get("/v1/subjects/E001", headers=HEADERS).json()["name"] == "Person A"
    # A rejected photo hands the token back; the next good upload with it still works once E001 is gone.
    tok = client.post("/v1/subjects/tokens", headers=HEADERS, json={"external_id": "NEW"}).json()["token"]
    bearer = {"Authorization": f"Bearer {tok}"}
    r = client.post("/v1/subjects", headers=bearer, files={"photo": ("a.jpg", b"garbage", "image/jpeg")})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "BAD_IMAGE"
    r = client.post("/v1/subjects", headers=bearer, files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 201, r.text
    assert client.post("/v1/subjects", headers=bearer,
                       files={"photo": ("a.jpg", person_crops[0], "image/jpeg")}).status_code == 401
    client.delete("/v1/subjects/NEW", headers=HEADERS)
    assert client.post("/v1/subjects/tokens", headers=HEADERS,
                       json={"external_id": "X", "token_ttl_seconds": 10**9}).status_code == 422


def test_deleting_a_project_kills_its_tokens(client, person_crops):
    p = client.post("/v1/projects", headers=ADMIN, json={"name": "doomed"}).json()
    tenant = {"X-API-Key": p["api_key"]}
    s = client.post("/v1/sessions", headers=tenant, json={}).json()
    tok = client.post("/v1/subjects/tokens", headers=tenant, json={"external_id": "D"}).json()["token"]
    assert client.delete(f"/v1/projects/{p['id']}", headers=ADMIN).status_code == 204
    assert run_stream(client, s, person_crops[0])[0]["reason_code"] == "SESSION_NOT_FOUND"
    assert client.post("/v1/subjects", headers={"Authorization": f"Bearer {tok}"},
                       files={"photo": ("a.jpg", person_crops[0], "image/jpeg")}).status_code == 401


def test_delete_subject_unlinks_audit_rows(client, person_crops):
    from sqlmodel import Session, select

    from app.db import get_engine
    from app.models import Verification

    assert _enrol(client, person_crops[0], "GONE").status_code == 201
    _, _, body = _run_session(client, person_crops[0], subject_id="GONE")
    assert body["ok"], body
    assert client.delete("/v1/subjects/GONE", headers=HEADERS).status_code == 204
    with Session(get_engine()) as db:
        rows = db.exec(select(Verification).where(Verification.subject_external_id == "GONE")).all()
        assert rows and all(v.subject_id is None for v in rows)


def test_project_key_refused_from_a_browser_origin(client, person_crops, enrolled):
    evil = {**HEADERS, "Origin": "https://app.example.com"}
    r = client.get("/v1/subjects", headers=evil)
    assert r.status_code == 401 and r.json()["detail"]["reason_code"] == "API_KEY_FROM_BROWSER"
    assert client.get("/v1/subjects", headers={**HEADERS, "Origin": "http://localhost:3010"}).status_code == 200
    assert client.get("/v1/subjects", headers={**HEADERS, "Origin": "http://127.0.0.1:5173"}).status_code == 200
    # A project can opt in while developing.
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"allow_browser_api_key": True}, "merge": True})
    try:
        assert client.get("/v1/subjects", headers=evil).status_code == 200
    finally:
        client.put("/v1/policy", headers=HEADERS, json={"overrides": {"allow_browser_api_key": False}, "merge": True})
    # Keys carry a prefix that secret scanners can match.
    p = client.post("/v1/projects", headers=ADMIN, json={"name": "prefixed"}).json()
    try:
        assert p["api_key"].startswith("lf_sk_")
        rotated = client.post(f"/v1/projects/{p['id']}/rotate-key", headers=ADMIN).json()["api_key"]
        assert rotated.startswith("lf_sk_") and rotated != p["api_key"]
    finally:
        client.delete(f"/v1/projects/{p['id']}", headers=ADMIN)


