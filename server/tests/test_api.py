import json

import pytest

from tests.conftest import ADMIN, HEADERS, make_meta


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


def _run_session(client, frame_bytes, subject_id="E001", meta_override=None, purpose="", headers=HEADERS):
    s = client.post("/v1/sessions", headers=headers, json={"subject_id": subject_id, "purpose": purpose}).json()
    challenges = s["challenges"]
    meta = meta_override(challenges, s["flash_colors"]) if meta_override \
        else make_meta(challenges, flash_colors=s["flash_colors"])
    files = [("frames", (f"{k}.jpg", frame_bytes, "image/jpeg")) for k in s["frame_kinds"]]
    data = {"meta": json.dumps(meta)}
    if subject_id:
        data["subject_id"] = subject_id
    r = client.post(f"/v1/sessions/{s['session_id']}/verify", headers=headers, data=data, files=files)
    return s, r


def test_verify_same_person_ok(client, person_crops, enrolled):
    s, r = _run_session(client, person_crops[0], purpose="checkin")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is True, body
    assert body["mode"] == "verify" and body["reason_code"] == "OK"
    assert body["scores"]["match"] > 0.9
    assert body["scores"]["spoof"] > 0.5
    assert body["verification_id"]


def test_verify_other_person_rejected(client, person_crops, enrolled):
    _, r = _run_session(client, person_crops[1])
    body = r.json()
    assert body["ok"] is False and body["reason_code"] == "NO_MATCH", body
    assert body["scores"]["match"] < 0.3


def test_liveness_only_session_needs_no_subject(client, person_crops):
    s, r = _run_session(client, person_crops[1], subject_id=None, purpose="kiosk")
    assert s["mode"] == "liveness"
    body = r.json()
    assert body["ok"] is True and body["mode"] == "liveness", body
    assert body["scores"]["match"] is None and body["scores"]["consistency"] > 0.9


def test_verify_too_fast_rejected(client, person_crops, enrolled):
    _, r = _run_session(client, person_crops[0], meta_override=lambda c, f: make_meta(c, step=50, flash_colors=f))
    assert r.json()["reason_code"] == "TIMING_TOO_FAST"


def test_session_carries_flash_and_client_config(client):
    s = client.post("/v1/sessions", headers=HEADERS, json={}).json()
    assert len(s["flash_colors"]) == 3 and len(set(s["flash_colors"])) == 3
    assert s["frame_kinds"] == ["neutral_start", "challenge_0", "challenge_1", "flash_0", "flash_1", "flash_2",
                                "neutral_end"]
    assert s["flash_hold_ms"] > 0
    assert s["client_config"]["parallax_min_shift"] == 0.08
    assert s["client_config"]["blink_max_ms"] == 600


def test_flash_shadow_mode_reports_scores(client, person_crops, enrolled):
    _, r = _run_session(client, person_crops[0])
    body = r.json()
    assert body["ok"] is True, body
    flash = body["details"]["flash"]
    assert flash["enforced"] is False and flash["response"] < 0.5


def test_smile_enforced_rejects_static_face(client, person_crops, enrolled):
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"smile_enforce": True}})
    try:
        _, r = _run_session(client, person_crops[0])
        body = r.json()
        assert body["reason_code"] == "EXPRESSION_MISMATCH", body
        assert body["details"]["smile"]["width_gain"] == 1.0
    finally:
        client.delete("/v1/policy", headers=HEADERS)


def test_flash_enforced_rejects_unlit_frames(client, person_crops, enrolled):
    client.put("/v1/policy", headers=HEADERS, json={"overrides": {"flash_enforce": True}})
    try:
        _, r = _run_session(client, person_crops[0])
        assert r.json()["reason_code"] == "FLASH_FAIL"
    finally:
        client.delete("/v1/policy", headers=HEADERS)


def test_session_single_use(client, person_crops, enrolled):
    s, r = _run_session(client, person_crops[0])
    assert r.status_code == 200
    files = [("frames", (f"{k}.jpg", person_crops[0], "image/jpeg")) for k in s["frame_kinds"]]
    r2 = client.post(f"/v1/sessions/{s['session_id']}/verify", headers=HEADERS,
                     data={"subject_id": "E001",
                           "meta": json.dumps(make_meta(s["challenges"], flash_colors=s["flash_colors"]))},
                     files=files)
    assert r2.status_code == 409


def test_unknown_subject(client, person_crops):
    _, r = _run_session(client, person_crops[0], subject_id="NOPE")
    assert r.status_code == 404


def test_verifications_listed_and_filtered(client, enrolled):
    rows = client.get("/v1/verifications", headers=HEADERS, params={"subject_id": "E001"}).json()
    assert any(r["ok"] for r in rows) and any(r["reason_code"] == "NO_MATCH" for r in rows)
    kiosk = client.get("/v1/verifications", headers=HEADERS, params={"purpose": "kiosk"}).json()
    assert kiosk and all(r["purpose"] == "kiosk" and r["subject_id"] is None for r in kiosk)


def test_policy_defaults_follow_environment(client):
    body = client.get("/v1/policy", headers=HEADERS).json()
    assert body["preset"] == "balanced" and body["overrides"] == {}
    assert body["effective"]["challenge_pool"] == "blink,smile"
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
        s, r = _run_session(client, person_crops[0])
        assert s["client_config"]["parallax_min_shift"] == 0.10
        assert r.json()["reason_code"] == "SPOOF"
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
