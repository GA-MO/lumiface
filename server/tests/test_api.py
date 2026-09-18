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
    _, r = _run_session(client, person_crops[0], subject_id="TMP")
    assert r.status_code == 200 and r.json()["ok"], r.text
    assert client.get("/v1/subjects/E001", headers=HEADERS).json()["expires_at"] is None  # policy default 0 keeps

    # Back-date the expiry: the subject vanishes from the API before the purge runs.
    with Session(get_engine()) as db:
        row = db.exec(select(Subject).where(Subject.external_id == "TMP")).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        db.add(row)
        db.commit()
    assert client.get("/v1/subjects/TMP", headers=HEADERS).status_code == 404
    assert "TMP" not in [s["external_id"] for s in client.get("/v1/subjects", headers=HEADERS).json()]
    _, r = _run_session(client, person_crops[0], subject_id="TMP")
    assert r.status_code == 404 and r.json()["detail"]["reason_code"] == "SUBJECT_NOT_FOUND"
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


def test_session_token_verifies_without_api_key(client, person_crops, enrolled):
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    assert s["session_token"]
    meta = make_meta(s["challenges"], flash_colors=s["flash_colors"])
    files = [("frames", (f"{k}.jpg", person_crops[0], "image/jpeg")) for k in s["frame_kinds"]]
    bearer = {"Authorization": f"Bearer {s['session_token']}"}
    # Wrong token: the session does not exist for this caller.
    r = client.post(f"/v1/sessions/{s['session_id']}/verify", headers={"Authorization": "Bearer nope"},
                    data={"meta": json.dumps(meta)}, files=files)
    assert r.status_code == 404
    r = client.post(f"/v1/sessions/{s['session_id']}/verify", headers={"Authorization": "Token x"},
                    data={"meta": json.dumps(meta)}, files=files)
    assert r.status_code == 401
    r = client.post(f"/v1/sessions/{s['session_id']}/verify", headers=bearer,
                    data={"meta": json.dumps(meta)}, files=files)
    assert r.status_code == 200 and r.json()["ok"], r.text
    # The token is only good for that one session.
    s2 = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    r = client.post(f"/v1/sessions/{s2['session_id']}/verify", headers=bearer,
                    data={"meta": json.dumps(meta)}, files=files)
    assert r.status_code == 404
    # No credentials at all.
    r = client.post(f"/v1/sessions/{s2['session_id']}/verify", data={"meta": json.dumps(meta)}, files=files)
    assert r.status_code == 401


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


def _bearer_verify(client, s, frame_bytes, meta=None, **form):
    meta = meta or make_meta(s["challenges"], flash_colors=s["flash_colors"])
    files = [("frames", (f"{k}.jpg", frame_bytes, "image/jpeg")) for k in s["frame_kinds"]]
    return client.post(f"/v1/sessions/{s['session_id']}/verify", headers={"Authorization": f"Bearer {s['session_token']}"},
                       data={"meta": json.dumps(meta), **form}, files=files)


def test_device_cannot_pick_the_subject(client, person_crops, enrolled):
    # A liveness session stays liveness: naming a subject is refused and the attempt is spent.
    s = client.post("/v1/sessions", headers=HEADERS, json={}).json()
    r = _bearer_verify(client, s, person_crops[0], subject_id="E001")
    assert r.status_code == 400 and r.json()["detail"]["reason_code"] == "SUBJECT_MISMATCH"
    r = _bearer_verify(client, s, person_crops[0], subject_id="NOPE")
    assert r.status_code == 409, "a refused attempt must consume the session, or it becomes a probe loop"
    # A bound session ignores nothing either.
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    r = _bearer_verify(client, s, person_crops[0], subject_id="E002")
    assert r.status_code == 400
    assert _bearer_verify(client, s, person_crops[0]).status_code == 409
    # The backend, holding the key, may still narrow a liveness session to a subject.
    _, r = _run_session(client, person_crops[0], subject_id="E001")
    assert r.status_code == 200


def test_backend_reads_session_outcome(client, person_crops, enrolled):
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001", "purpose": "login"}).json()
    bearer = {"Authorization": f"Bearer {s['session_token']}"}
    assert client.get(f"/v1/sessions/{s['session_id']}", headers=bearer).status_code == 401
    before = client.get(f"/v1/sessions/{s['session_id']}", headers=HEADERS).json()
    assert before["used"] is False and before["result"] is None and before["subject_id"] == "E001"
    r = _bearer_verify(client, s, person_crops[0])
    assert r.status_code == 200 and r.json()["ok"]
    after = client.get(f"/v1/sessions/{s['session_id']}", headers=HEADERS).json()
    assert after["used"] is True and after["result"]["ok"] is True
    assert after["result"]["verification_id"] == r.json()["verification_id"]
    rows = client.get("/v1/verifications", headers=HEADERS, params={"session_id": s["session_id"]}).json()
    assert [v["id"] for v in rows] == [r.json()["verification_id"]]
    # Another project cannot read it.
    other = client.post("/v1/projects", headers=ADMIN, json={"name": "other-tenant"}).json()
    try:
        assert client.get(f"/v1/sessions/{s['session_id']}", headers={"X-API-Key": other["api_key"]}).status_code == 404
    finally:
        client.delete(f"/v1/projects/{other['id']}", headers=ADMIN)


def test_bad_uploads_are_answered_not_crashed(client, person_crops, enrolled):
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    r = _bearer_verify(client, s, b"not a jpeg at all")
    assert r.status_code == 200 and r.json()["reason_code"] == "BAD_IMAGE"
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    r = client.post(f"/v1/sessions/{s['session_id']}/verify", headers={"Authorization": f"Bearer {s['session_token']}",
                    "Content-Length": str(64 * 1024 * 1024)}, content=b"")
    assert r.status_code == 413
    s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
    r = client.post(f"/v1/sessions/{s['session_id']}/verify", headers={"Authorization": f"Bearer {s['session_token']}"},
                    data={"meta": "{not json"}, files=[("frames", ("a.jpg", person_crops[0], "image/jpeg"))])
    assert r.status_code == 422 and "VerifyMeta" not in r.text and "pydantic" not in r.text
    # httpx refuses to send non-ASCII headers; the parser and the compare must not 500 on them either way.
    from fastapi import HTTPException

    from app.deps import bearer_token, token_matches

    with pytest.raises(HTTPException) as e:
        bearer_token("Bearer é")
    assert e.value.status_code == 401
    assert token_matches("é", "abc") is False and bearer_token("Basic dXNlcjpwYXNz") is None


def test_stored_frames_use_server_names(client, person_crops, enrolled, tmp_path):
    from app.config import get_settings

    settings = get_settings()
    settings.store_frames, settings.frames_dir = True, str(tmp_path)
    try:
        s = client.post("/v1/sessions", headers=HEADERS, json={"subject_id": "E001"}).json()
        meta = make_meta(s["challenges"], flash_colors=s["flash_colors"])
        meta["frames"][0]["kind"] = "/tmp/pwned"
        meta["frames"][1]["kind"] = "../../escape"
        r = _bearer_verify(client, s, person_crops[1], meta=meta)  # wrong person and wrong kinds: a failure gets stored
        assert r.status_code == 200 and not r.json()["ok"]
        written = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.jpg"))
        assert written and all(w.startswith(f"1/{s['session_id']}/") for w in written), written
        assert not any("pwned" in w or "escape" in w for w in written)
    finally:
        settings.store_frames, settings.frames_dir = False, "data/frames"


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
    assert _bearer_verify(client, s, person_crops[0]).status_code == 404
    assert client.post("/v1/subjects", headers={"Authorization": f"Bearer {tok}"},
                       files={"photo": ("a.jpg", person_crops[0], "image/jpeg")}).status_code == 401


def test_delete_subject_unlinks_audit_rows(client, person_crops):
    from sqlmodel import Session, select

    from app.db import get_engine
    from app.models import Verification

    assert _enrol(client, person_crops[0], "GONE").status_code == 201
    _, r = _run_session(client, person_crops[0], subject_id="GONE")
    assert r.status_code == 200
    assert client.delete("/v1/subjects/GONE", headers=HEADERS).status_code == 204
    with Session(get_engine()) as db:
        rows = db.exec(select(Verification).where(Verification.subject_external_id == "GONE")).all()
        assert rows and all(v.subject_id is None for v in rows)
