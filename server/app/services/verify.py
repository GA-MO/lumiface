"""Shared verdict types and the per-face checks (single face, pose, consistency) used by enrolment and the stream."""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..policy import get_policy
from .antispoof import get_antispoof
from .face import BadImage, FaceResult, cosine, decode_image, get_face_engine


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
    s = get_policy()
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
    s = get_policy()
    try:
        img = decode_image(photo)
    except BadImage:
        return EnrollResult(False, "BAD_IMAGE")
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
    s = get_policy()
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
    s = get_policy()
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
