"""Verification pipeline: timing -> face/spoof per frame -> pose -> match -> consistency."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..config import get_settings
from .antispoof import get_antispoof
from .challenge import VerifyMeta, validate_timing
from .expression import mouth_metrics, smile_ok
from .face import FaceResult, cosine, decode_image, get_face_engine
from .flash import face_patch_mean_rgb, flash_passes, score_flash, surroundings_mean_rgb


@dataclass
class VerifyResult:
    ok: bool
    reason_code: str
    match_score: float | None = None
    spoof_score: float | None = None
    consistency_score: float | None = None
    details: dict = field(default_factory=dict)


@dataclass
class EnrollResult:
    ok: bool
    reason_code: str
    embedding: np.ndarray | None = None
    spoof_score: float | None = None
    details: dict = field(default_factory=dict)


def _single_face(img) -> tuple[FaceResult | None, str | None]:
    s = get_settings()
    faces = get_face_engine().analyze(img)
    if not faces:
        return None, "NO_FACE"
    if len(faces) > 1:
        # allow small background faces: keep only faces >= 40% of the largest
        big = [f for f in faces if f.area >= 0.4 * faces[0].area]
        if len(big) > 1:
            return None, "MULTIPLE_FACES"
    f = faces[0]
    if min(f.width, f.height) < s.min_face_size:
        return None, "FACE_TOO_SMALL"
    return f, None


def enroll(photo: bytes) -> EnrollResult:
    s = get_settings()
    img = decode_image(photo)
    face, err = _single_face(img)
    if err:
        return EnrollResult(False, err)
    assert face is not None
    if abs(face.yaw) > s.enroll_max_yaw or abs(face.pitch) > s.enroll_max_pitch:
        return EnrollResult(False, "POSE_NOT_FRONTAL", details={"yaw": face.yaw, "pitch": face.pitch})
    sp = get_antispoof().score(img, face.bbox)
    if sp.real < s.spoof_threshold or (sp.cvpr is not None and sp.cvpr < s.cvpr_threshold):
        return EnrollResult(False, "SPOOF", spoof_score=sp.real, details={**sp.per_model, "cvpr": sp.cvpr})
    return EnrollResult(True, "OK", embedding=face.embedding, spoof_score=sp.real,
                        details={"yaw": face.yaw, "pitch": face.pitch, **sp.per_model, "cvpr": sp.cvpr})


def _pose_ok(challenge: str, face: FaceResult) -> bool:
    s = get_settings()
    if challenge in ("turn_left", "turn_right"):
        if abs(face.yaw) < s.turn_min_yaw:
            return False
        if s.turn_strict_direction:
            # Observed on un-mirrored uploads: insightface yaw is positive when the
            # subject turns to their own right (check-in #1 on the Android emulator: +45).
            want_positive = challenge == "turn_right"
            return (face.yaw > 0) == want_positive
        return True
    if challenge == "nod":
        return abs(face.pitch) >= s.nod_min_pitch
    return True


def _consistency(faces: list[FaceResult]) -> tuple[float, bool]:
    """Same person in every frame. Frontal frames must agree closely; a frame taken
    mid turn/nod only has to clear the looser pose threshold against each other frame."""
    s = get_settings()
    frontal = [abs(f.yaw) <= s.pose_frame_max_angle and abs(f.pitch) <= s.pose_frame_max_angle for f in faces]
    worst, ok = 1.0, True
    for i, a in enumerate(faces):
        for j, b in enumerate(faces):
            if j <= i:
                continue
            sim = cosine(a.embedding, b.embedding)
            worst = min(worst, sim)
            bar = s.consistency_threshold if frontal[i] and frontal[j] else s.consistency_pose_threshold
            if sim < bar:
                ok = False
    return float(worst), ok


def verify(frames: list[bytes], meta: VerifyMeta, challenges: list[str], enrolled: np.ndarray,
           flash_colors: list[str] | None = None) -> VerifyResult:
    s = get_settings()
    flash_colors = flash_colors or []
    if len(frames) != len(meta.frames):
        return VerifyResult(False, "FRAME_COUNT")
    if reason := validate_timing(meta, challenges, flash_colors):
        return VerifyResult(False, reason)

    faces: list[FaceResult] = []
    spoof_scores: list[float] = []
    cvpr_scores: list[float] = []
    per_frame: list[dict] = []
    flash_rgb: list[np.ndarray] = []
    flash_bg_rgb: list[np.ndarray] = []
    for i, (data, fm) in enumerate(zip(frames, meta.frames)):
        img = decode_image(data)
        if fm.kind.startswith("flash_"):
            # Tinted frames only feed the reflection check. Detection may fail
            # under a strong tint, so fall back to the last frontal box.
            found = get_face_engine().analyze(img)
            bbox = found[0].bbox if found else (faces[-1].bbox if faces else None)
            if bbox is None:
                return VerifyResult(False, "NO_FACE", details={"frame": fm.kind})
            flash_rgb.append(face_patch_mean_rgb(img, bbox))
            flash_bg_rgb.append(surroundings_mean_rgb(img, bbox))
            continue
        face, err = _single_face(img)
        if err:
            return VerifyResult(False, err, details={"frame": fm.kind})
        assert face is not None
        sp = get_antispoof().score(img, face.bbox)
        faces.append(face)
        spoof_scores.append(sp.real)
        if sp.cvpr is not None:
            cvpr_scores.append(sp.cvpr)
        per_frame.append({"kind": fm.kind, "spoof": round(sp.real, 4),
                          "cvpr": None if sp.cvpr is None else round(sp.cvpr, 4),
                          "yaw": round(face.yaw, 1), "pitch": round(face.pitch, 1), "det": round(face.det_score, 3)})

    spoof_mean = float(np.mean(spoof_scores))
    details = {"frames": per_frame}
    if spoof_mean < s.spoof_threshold or min(spoof_scores) < s.spoof_hard_floor:
        return VerifyResult(False, "SPOOF", spoof_score=spoof_mean, details={**details, "gate": "minifasnet"})
    if cvpr_scores:
        cvpr_mean = float(np.mean(cvpr_scores))
        details["cvpr_mean"] = round(cvpr_mean, 4)
        if cvpr_mean < s.cvpr_threshold or min(cvpr_scores) < s.cvpr_hard_floor:
            return VerifyResult(False, "SPOOF", spoof_score=spoof_mean, details={**details, "gate": "cvpr2024"})

    for i, ch in enumerate(challenges):
        if not _pose_ok(ch, faces[i + 1]):
            return VerifyResult(False, "POSE_MISMATCH", spoof_score=spoof_mean,
                                details={**details, "challenge": ch})
        if ch == "smile":
            ok, info = smile_ok(mouth_metrics(faces[0].landmarks), mouth_metrics(faces[i + 1].landmarks))
            details["smile"] = {**info, "enforced": s.smile_enforce}
            if s.smile_enforce and not ok:
                return VerifyResult(False, "EXPRESSION_MISMATCH", spoof_score=spoof_mean,
                                    details={**details, "challenge": ch})

    if flash_colors:
        fr = score_flash(flash_rgb, flash_colors, flash_bg_rgb)
        details["flash"] = {"correlation": round(fr.correlation, 3), "response": round(fr.response, 2),
                            "order_ok": fr.order_ok, "deltas": fr.per_frame,
                            "background_ratio": None if fr.background_ratio is None else round(fr.background_ratio, 2),
                            "enforced": s.flash_enforce}
        if s.flash_enforce and not flash_passes(fr):
            return VerifyResult(False, "FLASH_FAIL", spoof_score=spoof_mean, details=details)

    match_scores = [cosine(f.embedding, enrolled) for f in faces]
    match_min = float(min(match_scores))
    details["match"] = [round(m, 4) for m in match_scores]
    if match_min < s.match_threshold:
        return VerifyResult(False, "NO_MATCH", match_score=match_min, spoof_score=spoof_mean, details=details)

    consistency, consistent = _consistency(faces)
    if not consistent:
        return VerifyResult(False, "INCONSISTENT", match_score=match_min, spoof_score=spoof_mean,
                            consistency_score=consistency, details=details)

    return VerifyResult(True, "OK", match_score=match_min, spoof_score=spoof_mean,
                        consistency_score=consistency, details=details)
