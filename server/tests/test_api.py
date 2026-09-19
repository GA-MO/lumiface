import base64
import json

import pytest
from sqlmodel import Session

from app.db import get_engine
from app.models import VerifySession

from tests.conftest import ADMIN, HEADERS, blank_jpeg, run_stream


def test_health(client):
    body = client.get("/health").json()
    assert body["ok"] is True and "strict" in body["presets"]


def test_auth_required(client):
    assert client.get("/v1/verifications").status_code == 401
    assert client.get("/v1/verifications", headers={"X-API-Key": "nope"}).status_code == 401


def test_debug_score_real_face(client, person_crops):
    r = client.post("/v1/debug/score", headers=HEADERS, files={"photo": ("a.jpg", person_crops[0], "image/jpeg")})
    assert r.status_code == 200, r.text
    face = r.json()[0]
    assert face["spoof_real"] > 0.5
    assert len(face["embedding"]) == 512


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


@pytest.fixture(scope="module")
def reference(person_crops):
    """Person A's photo as the backend would send it: base64, straight from its own records."""
    return _b64(person_crops[0])


def _session(client, reference=None, purpose="", headers=HEADERS):
    body = {"reference_photo": reference, "purpose": purpose} if reference else {"purpose": purpose}
    r = client.post("/v1/sessions", headers=headers, json=body)
    assert r.status_code == 201, r.text
    return r.json()


def _run_session(client, frame_bytes, reference=None, purpose="", headers=HEADERS, **kw):
    """Backend creates the session (with the reference photo, or none for liveness); the device streams it.
    Returns (session, plan, result message)."""
    sess = _session(client, reference, purpose, headers)
    plan, result = run_stream(client, sess, frame_bytes, **kw)
    return sess, plan, result


def test_verify_same_person_ok(client, person_crops, reference):
    s, plan, body = _run_session(client, person_crops[0], reference, purpose="checkin")
    assert "challenges" not in s and "flash_colors" not in s, "the plan only travels over the stream"
    assert plan["challenges"] == ["face_move"] and len(plan["flash_colors"]) == 3 and plan["client_config"]["align_hold_ms"]
    assert plan["oval"] == {"cx": 0.5, "cy": 0.45, "width": 0.35, "height_ratio": 1.35}
    assert body["type"] == "result" and body["ok"] is True, body
    assert body["mode"] == "verify" and body["reason_code"] == "OK"
    assert body["scores"]["match"] > 0.9 and body["scores"]["spoof"] > 0.5
    assert body["verification_id"] and body["details"] == {}, "no per-frame scores for the device"


def test_verify_other_person_rejected(client, person_crops, reference):
    _, _, body = _run_session(client, person_crops[1], reference)
    assert body["ok"] is False and body["reason_code"] == "NO_MATCH", body
    assert body["scores"]["match"] < 0.3


def test_liveness_only_session_needs_no_photo(client, person_crops):
    s, _, body = _run_session(client, person_crops[1], purpose="kiosk")
    assert s["mode"] == "liveness"
    assert body["ok"] is True and body["mode"] == "liveness", body
    assert body["scores"]["match"] is None and body["scores"]["consistency"] > 0.9


def test_reference_photo_lives_only_until_the_stream_claims_it(client, person_crops, reference):
    """The backend hands over its own photo of the person; the server keeps its embedding for the session and no longer."""
    s = _session(client, reference, purpose="login")
    assert s["mode"] == "verify"
    with Session(get_engine()) as db:
        row = db.get(VerifySession, s["session_id"])
        assert row.reference is True and len(row.reference_embedding) == 512 * 4
    _, body = run_stream(client, s, person_crops[0])
    assert body["ok"] is True and body["mode"] == "verify" and body["scores"]["match"] > 0.9, body
    with Session(get_engine()) as db:
        row = db.get(VerifySession, s["session_id"])
        assert row.reference_embedding is None, "the embedding is dropped when the stream claims the session"
    status = client.get(f"/v1/sessions/{s['session_id']}", headers=HEADERS).json()
    assert status["mode"] == "verify" and status["reference"] is True and status["result"]["mode"] == "verify"
    rows = client.get("/v1/verifications", headers=HEADERS, params={"session_id": s["session_id"]}).json()
    assert rows[0]["reference"] is True


def test_reference_photo_data_url_and_turned_face(client, person_crops):
    s = client.post("/v1/sessions", headers=HEADERS,
                    json={"reference_photo": "data:image/jpeg;base64," + _b64(person_crops[0])}).json()
    _, body = run_stream(client, s, person_crops[1])
    assert body["ok"] is False and body["reason_code"] == "NO_MATCH", body
    # Person B is turned away in the sample photo: a reference must be frontal, and the answer comes at creation.
    r = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": _b64(person_crops[1])})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "POSE_NOT_FRONTAL", r.text


def test_face_swapped_in_for_the_flash_is_caught(client, person_crops, reference):
    """Identity is read on the flash frames too: person A aligns, fills the oval and ends the session,
    person B is in front of the camera while the colours show. No key frame sees B; the flash frames do."""
    s, _, body = _run_session(client, person_crops[0], reference, flash_jpeg=person_crops[1])
    assert body["ok"] is False and body["reason_code"] == "NO_MATCH", body
    d = _details(client, s["session_id"])
    kinds = [k["kind"] for k in d["key_frames"]]
    assert kinds == ["neutral_start", "challenge_0", "neutral_end", "flash_0", "flash_1", "flash_2"]
    key, flash = d["match"][:3], d["match"][3:]
    assert min(key) > 0.9 and max(flash) < 0.3, d["match"]
    assert d["gates"]["consistency"] == "INCONSISTENT"
    # And a liveness session with the same swap fails on consistency alone.
    s, _, body = _run_session(client, person_crops[0], flash_jpeg=person_crops[1])
    assert body["ok"] is False and body["reason_code"] == "INCONSISTENT", body


def test_reference_photo_is_checked_at_creation(client, person_crops):
    r = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": "not base64!"})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "BAD_IMAGE"
    r = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": _b64(b"\xff\xd8garbage")})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "BAD_IMAGE"
    r = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": _b64(blank_jpeg())})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "NO_FACE", r.text
    r = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": _b64(b"x" * (5 * 1024 * 1024))})
    assert r.status_code == 413 and r.json()["detail"]["reason_code"] == "PAYLOAD_TOO_LARGE"


def test_too_fast_on_the_server_clock(client, person_crops, reference):
    # The device's own timestamps are ignored: the server measures the session on its clock.
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"min_session_ms": 1500}})
    try:
        _, _, body = _run_session(client, person_crops[0], reference)
        assert body["reason_code"] == "TIMING_TOO_FAST", body
        _, _, body = _run_session(client, person_crops[0], reference, pause=1.6)
        assert body["ok"] is True, body
    finally:
        client.delete("/v1/policy", headers=HEADERS)


def test_events_out_of_order_are_rejected(client, person_crops, reference):
    _, _, body = _run_session(client, person_crops[0], reference, order=["challenge_done:0", "aligned", "frames"])
    assert body["reason_code"] == "TIMING_ORDER"
    _, _, body = _run_session(client, person_crops[0], reference, order=["aligned", "frames"])  # never finished the plan
    assert body["reason_code"] == "TIMING_ORDER"


def test_frozen_feed_is_rejected(client, person_crops, reference):
    sess = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": reference}).json()
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
    assert s["client_config"]["move_start_max_ratio"] == 0.8
    assert s["client_config"]["oval_hold_ms"] == 500


def _details(client, session_id):
    from sqlmodel import Session, select

    from app.db import get_engine
    from app.models import Verification

    with Session(get_engine()) as db:
        row = db.exec(select(Verification).where(Verification.session_id == session_id)).one()
        return json.loads(row.details)


def test_still_face_does_not_move(client, person_crops, reference):
    s, plan, body = _run_session(client, person_crops[0], reference, move=False)
    assert body["reason_code"] == "MOVEMENT_MISMATCH", body
    d = _details(client, s["session_id"])
    assert d["challenge_0"]["name"] == "face_move" and d["challenge_0"]["growth"] == 1.0


def test_moving_face_is_measured(client, person_crops, reference):
    s, plan, body = _run_session(client, person_crops[0], reference)
    assert body["ok"] is True, body
    d = _details(client, s["session_id"])["challenge_0"]
    assert 1.8 < d["growth"] < 2.3 and d["fill"] >= 0.85 and d["centred"]


def test_h264_access_units_verify_like_jpeg(client, person_crops, reference):
    """The phone plugins send one H.264 access unit per frame; the server decodes and judges the same way."""
    s, _, body = _run_session(client, person_crops[0], reference, fmt="h264")
    assert body["ok"] is True, body
    d = _details(client, s["session_id"])
    assert d["client"]["format"] == "h264" and d["frames"] >= 8
    assert 1.8 < d["challenge_0"]["growth"] < 2.3 and d["placement"] == "client"


def test_webm_recording_verifies_like_jpeg(client, person_crops, reference):
    """A browser records the whole session with MediaRecorder; the frames get their times from the video."""
    s, _, body = _run_session(client, person_crops[0], reference, fmt="webm")
    assert body["ok"] is True, body
    d = _details(client, s["session_id"])
    assert d["client"]["format"] == "webm" and d["frames"] >= 8
    assert 1.8 < d["challenge_0"]["growth"] < 2.3


def test_unknown_stream_format_is_refused(client, person_crops, reference):
    sess = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": reference}).json()
    with client.websocket_connect(f"/v1/sessions/{sess['session_id']}/stream") as ws:
        ws.send_json({"type": "hello", "token": sess["session_token"], "format": "avi"})
        assert ws.receive_json() == {"type": "error", "reason_code": "HELLO_INVALID"}


def test_flash_shadow_mode_reports_scores(client, person_crops, reference):
    s, _, body = _run_session(client, person_crops[0], reference)
    assert body["ok"] is True, body
    d = _details(client, s["session_id"])
    assert d["flash"]["enforced"] is False and d["flash"]["response"] < 0.5
    assert [e["name"] for e in d["events"]] == ["aligned", "challenge_done", "flash", "flash", "flash", "flash_end", "end"]
    assert d["client"] == {"platform": "test", "user_agent": "testclient", "format": "jpeg"} and d["frames"] >= 8


def test_flash_enforced_rejects_unlit_frames(client, person_crops, reference):
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"flash_enforce": True}})
    try:
        s, _, body = _run_session(client, person_crops[0], reference)
        assert body["reason_code"] == "FLASH_FAIL"
    finally:
        client.delete("/v1/policy", headers=HEADERS)
    # The gates after the one that refused still ran: the backend sees every score without a replay.
    d = _details(client, s["session_id"])
    assert d["gates"] == {"frames": "pass", "order": "pass", "timing": "pass", "static": "pass",
                          "neutral_start": "pass", "challenge_0": "pass", "flash": "FLASH_FAIL", "neutral_end": "pass",
                          "minifasnet": "pass", "cvpr2024": "pass", "match": "pass", "consistency": "pass"}
    assert d["flash"]["enforced"] is True and len(d["match"]) == 6 and 0 < d["consistency"] <= 1
    assert all(0 <= f["spoof"] <= 1 and 0 <= f["cvpr"] <= 1 for f in d["key_frames"] if not f["kind"].startswith("flash"))
    assert [f["kind"] for f in d["key_frames"]][3:] == ["flash_0", "flash_1", "flash_2"], "flash frames carry identity only"
    row = client.get("/v1/verifications", headers=HEADERS).json()[0]
    assert row["reason_code"] == "FLASH_FAIL" and row["match_score"] and row["spoof_score"]


def test_still_face_is_judged_by_every_gate(client, person_crops, reference):
    s, _, body = _run_session(client, person_crops[0], reference, move=False)
    assert body["reason_code"] == "MOVEMENT_MISMATCH"
    d = _details(client, s["session_id"])
    assert d["gates"]["challenge_0"] == "MOVEMENT_MISMATCH" and d["gates"]["match"] == "pass"
    assert d["challenge"] == "face_move" and "gate" not in d and "window" not in d


def test_session_single_use(client, person_crops, reference):
    s, _, body = _run_session(client, person_crops[0], reference)
    assert body["ok"] is True
    again, _ = run_stream(client, s, person_crops[0])
    assert again == {"type": "error", "reason_code": "SESSION_USED"}


def test_verifications_listed_and_filtered(client, reference):
    rows = client.get("/v1/verifications", headers=HEADERS, params={"ok": "false"}).json()
    assert rows and all(r["ok"] is False for r in rows) and any(r["reason_code"] == "NO_MATCH" for r in rows)
    kiosk = client.get("/v1/verifications", headers=HEADERS, params={"purpose": "kiosk"}).json()
    assert kiosk and all(r["purpose"] == "kiosk" and r["reference"] is False for r in kiosk)


def test_policy_defaults_follow_environment(client):
    body = client.get("/v1/policy", headers=HEADERS).json()
    assert body["preset"] == "balanced" and body["overrides"] == {}
    assert body["effective"]["oval_width_fraction"] == 0.35
    assert body["effective"]["min_face_size"] == 60
    assert body["effective"]["client"]["move_start_max_ratio"] == 0.8


def test_policy_presets_listed_with_schema(client):
    presets = {p["name"]: p for p in client.get("/v1/policy/presets", headers=HEADERS).json()}
    assert set(presets) == {"balanced", "strict", "relaxed", "emulator"}
    assert presets["strict"]["effective"]["move_min_growth"] == 1.4
    assert presets["emulator"]["effective"]["flash_enforce"] is False
    schema = client.get("/v1/policy/schema", headers=HEADERS).json()
    names = {f["name"] for f in schema}
    assert {"match_threshold", "oval_width_fraction", "client.oval_min_fill"} <= names
    assert all(f["description"] for f in schema)


def test_policy_update_rejects_unknown_field(client):
    r = client.put("/v1/policy", headers=HEADERS, json={"overrides": {"no_such_field": 1}})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "POLICY_INVALID"
    r = client.put("/v1/policy", headers=HEADERS, json={"preset": "paranoid"})
    assert r.status_code == 422 and r.json()["detail"]["reason_code"] == "UNKNOWN_PRESET"


def test_strict_preset_rejects_the_same_person_at_higher_bar(client, person_crops, reference):
    r = client.put("/v1/policy", headers=HEADERS,
                   json={"preset": "strict", "overrides": {"spoof_threshold": 0.999}})
    assert r.status_code == 200, r.text
    assert r.json()["effective"]["flash_min_correlation"] == 0.7
    try:
        s, _, body = _run_session(client, person_crops[0], reference)
        assert s["client_config"]["oval_min_fill"] == 0.9
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
    assert client.get("/v1/verifications", headers=tenant).json() == []
    assert client.post("/v1/projects", headers=ADMIN, json={"name": "kiosk-app"}).status_code == 409
    listed = {p["name"]: p for p in client.get("/v1/projects", headers=ADMIN).json()}
    assert listed["kiosk-app"]["api_key"] is None and listed["kiosk-app"]["verifications"] == 0
    rotated = client.post(f"/v1/projects/{created['id']}/rotate-key", headers=ADMIN).json()["api_key"]
    assert rotated != key
    assert client.get("/v1/verifications", headers=tenant).status_code == 401
    assert client.delete(f"/v1/projects/{created['id']}", headers=ADMIN).status_code == 204


def test_session_token_is_the_only_way_in(client, person_crops, reference):
    s = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": reference}).json()
    assert s["session_token"]
    # Wrong or missing token: the session does not exist for this caller, and nothing is spent.
    assert run_stream(client, s, person_crops[0], token="nope")[0] == {"type": "error", "reason_code": "SESSION_NOT_FOUND"}
    assert run_stream(client, s, person_crops[0], token="")[0]["reason_code"] == "SESSION_NOT_FOUND"
    with client.websocket_connect(f"/v1/sessions/{s['session_id']}/stream") as ws:
        ws.send_json({"type": "nope"})
        assert ws.receive_json()["reason_code"] == "HELLO_INVALID"
    # The right token, and only for that one session.
    s2 = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": reference}).json()
    assert run_stream(client, s2, person_crops[0], token=s["session_token"])[0]["reason_code"] == "SESSION_NOT_FOUND"
    _, body = run_stream(client, s, person_crops[0])
    assert body["ok"] is True, body
    assert client.get(f"/v1/sessions/{s['session_id']}", headers=HEADERS).json()["used"] is True


def test_device_cannot_pick_who_to_match(client, person_crops):
    # The reference is fixed by the backend at creation; the stream has no field to name one, and a
    # liveness session stays liveness whatever the device streams.
    s = client.post("/v1/sessions", headers=HEADERS, json={}).json()
    _, body = run_stream(client, s, person_crops[1])
    assert body["ok"] is True and body["mode"] == "liveness" and body["scores"]["match"] is None
    rows = client.get("/v1/verifications", headers=HEADERS, params={"session_id": s["session_id"]}).json()
    assert rows[0]["reference"] is False


def test_backend_reads_session_outcome(client, person_crops, reference):
    s = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": reference, "purpose": "login"}).json()
    bearer = {"Authorization": f"Bearer {s['session_token']}"}
    assert client.get(f"/v1/sessions/{s['session_id']}", headers=bearer).status_code == 401
    before = client.get(f"/v1/sessions/{s['session_id']}", headers=HEADERS).json()
    assert before["used"] is False and before["result"] is None and before["reference"] is True
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


def test_bad_uploads_are_answered_not_crashed(client, person_crops, reference):
    # Undecodable frames simply show no face.
    _, _, body = _run_session(client, b"not a jpeg at all", reference)
    assert body["type"] == "result" and body["reason_code"] == "NO_FACE"
    # An oversized frame ends the stream.
    from app.config import get_settings

    s = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": reference}).json()
    with client.websocket_connect(f"/v1/sessions/{s['session_id']}/stream") as ws:
        ws.send_json({"type": "hello", "token": s["session_token"]})
        assert ws.receive_json()["type"] == "plan"
        ws.send_bytes((0).to_bytes(8, "big") + b"x" * (get_settings().max_frame_bytes + 1))
        assert ws.receive_json()["reason_code"] == "PAYLOAD_TOO_LARGE"
    # Garbage where an event should be.
    s = client.post("/v1/sessions", headers=HEADERS, json={"reference_photo": reference}).json()
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


def test_deleting_a_project_kills_its_sessions(client, person_crops):
    p = client.post("/v1/projects", headers=ADMIN, json={"name": "doomed"}).json()
    tenant = {"X-API-Key": p["api_key"]}
    s = client.post("/v1/sessions", headers=tenant, json={}).json()
    assert client.delete(f"/v1/projects/{p['id']}", headers=ADMIN).status_code == 204
    assert run_stream(client, s, person_crops[0])[0]["reason_code"] == "SESSION_NOT_FOUND"


def test_project_key_refused_from_a_browser_origin(client):
    evil = {**HEADERS, "Origin": "https://app.example.com"}
    r = client.get("/v1/verifications", headers=evil)
    assert r.status_code == 401 and r.json()["detail"]["reason_code"] == "API_KEY_FROM_BROWSER"
    assert client.get("/v1/verifications", headers={**HEADERS, "Origin": "http://localhost:3010"}).status_code == 200
    assert client.get("/v1/verifications", headers={**HEADERS, "Origin": "http://127.0.0.1:5173"}).status_code == 200
    # A project can opt in while developing.
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"allow_browser_api_key": True}, "merge": True})
    try:
        assert client.get("/v1/verifications", headers=evil).status_code == 200
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


