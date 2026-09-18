"""Per-project verification policy: every tunable the server and the client apply.

Environment variables (Settings) are the defaults of the `balanced` preset. A project
picks a preset and may override single fields; the effective policy is resolved per
request and read by the services through `get_policy()`.
"""
from __future__ import annotations

import json
from contextvars import ContextVar
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .config import get_settings

ALL_CHALLENGES = ("blink", "turn_left", "turn_right", "smile", "nod")


class ClientPolicy(BaseModel):
    """Tunables the app applies while running the challenges. Sent with every session."""

    model_config = ConfigDict(extra="forbid")

    align_hold_ms: int = Field(600, description="Face must stay aligned this long before the first frame.")
    min_face_width_fraction: float = Field(0.28, description="Face box width / frame width lower bound.")
    max_face_width_fraction: float = Field(0.75, description="Face box width / frame width upper bound.")
    center_tolerance: float = Field(0.18, description="Allowed offset of the face centre from the frame centre.")
    neutral_max_yaw: float = Field(15, description="Max |yaw| in degrees for a neutral frame.")
    neutral_max_pitch: float = Field(15, description="Max |pitch| in degrees for a neutral frame.")
    challenge_timeout_ms: int = Field(10000, description="Give up on a challenge after this long.")
    face_lost_grace_ms: int = Field(1500, description="Fail when no face is seen for this long.")
    eye_open_threshold: float = Field(0.6, description="Eye-open probability that counts as open.")
    eye_closed_threshold: float = Field(0.25, description="Eye-open probability that counts as closed.")
    blink_min_ms: int = Field(40, description="Shortest genuine blink.")
    blink_max_ms: int = Field(600, description="Longest genuine blink.")
    smile_threshold: float = Field(0.7, description="Smile probability that counts as smiling.")
    smile_baseline_max: float = Field(0.4, description="Smile probability must start below this.")
    smile_hold_ms: int = Field(300, description="Smile must be held this long.")
    turn_min_yaw: float = Field(25, description="Head yaw in degrees that counts as a turn.")
    turn_hold_ms: int = Field(200, description="Turn must be held this long.")
    parallax_min_shift: float = Field(0.08, description="Min nose parallax change during a turn; 0 disables.")
    parallax_when_no_turn: bool = Field(True, description="Append a client-only turn when the server picked none.")
    nod_min_pitch: float = Field(15, description="Head pitch in degrees that counts as a nod.")
    nod_hold_ms: int = Field(200, description="Nod must be held this long.")
    settle_after_challenge_ms: int = Field(400, description="Pause after a challenge before capturing.")
    settle_after_flash_ms: int = Field(800, description="Pause after the last flash colour before neutral_end.")


class Policy(BaseModel):
    """Everything a project can tune. Field defaults mirror the environment defaults."""

    model_config = ConfigDict(extra="forbid")

    match_threshold: float = Field(description="Min cosine similarity between every frame and the enrolled face.")
    consistency_threshold: float = Field(description="Min cosine similarity between two frontal frames.")
    consistency_pose_threshold: float = Field(description="Min similarity when one frame is mid turn/nod.")
    pose_frame_max_angle: float = Field(description="|yaw| or |pitch| above this marks a pose frame.")
    spoof_threshold: float = Field(description="MiniFASNet real score, mean over frames.")
    spoof_hard_floor: float = Field(description="MiniFASNet real score every single frame must clear.")
    cvpr_enabled: bool = Field(description="Run the CVPR-2024 ResNet50 gate on a face crop.")
    cvpr_crop_margin: float = Field(description="Face crop margin for the CVPR gate.")
    cvpr_threshold: float = Field(description="CVPR live probability, mean over frames.")
    cvpr_hard_floor: float = Field(description="CVPR live probability every frame must clear.")
    min_face_size: int = Field(description="Min face box side in pixels.")
    enroll_max_yaw: float = Field(description="Max |yaw| accepted for an enrolment photo.")
    enroll_max_pitch: float = Field(description="Max |pitch| accepted for an enrolment photo.")
    turn_min_yaw: float = Field(description="Server-side yaw a turn frame must show.")
    nod_min_pitch: float = Field(description="Server-side pitch a nod frame must show.")
    turn_strict_direction: bool = Field(description="Require the turn to go the commanded way.")
    smile_enforce: bool = Field(description="Reject when the server cannot see the smile itself.")
    smile_min_width_gain: float = Field(description="Mouth width gain vs the neutral frame.")
    smile_min_lift: float = Field(description="Mouth corner lift vs the neutral frame (inter-ocular units).")

    session_ttl_seconds: int = Field(description="A session must be verified within this time.")
    subject_ttl_seconds: int = Field(description="Default retention of an enrolled face in seconds; 0 keeps it until deleted.")
    allow_browser_api_key: bool = Field(description="Accept the project key from a browser origin other than localhost. Development only.")
    challenge_count: int = Field(description="Challenges per session.")
    challenge_pool: str = Field(description="Comma separated pool: blink, turn_left, turn_right, smile, nod.")
    required_challenge: str = Field(description="Always included when in the pool; empty for none.")
    min_challenge_ms: int = Field(description="Shortest accepted challenge duration.")
    max_challenge_ms: int = Field(description="Longest accepted challenge duration.")
    min_session_ms: int = Field(description="Shortest accepted whole session.")

    flash_count: int = Field(description="Screen-flash colours per session; 0 disables.")
    flash_enforce: bool = Field(description="Reject on flash failure; false records scores only.")
    flash_min_correlation: float = Field(description="Min correlation between commanded and seen colour sequence.")
    flash_min_response: float = Field(description="Min RMS chroma change on the face, 8-bit units.")
    flash_max_background_ratio: float = Field(description="Max surroundings/face flash response.")
    flash_hold_ms: int = Field(description="How long the app shows each colour.")

    client: ClientPolicy = Field(default_factory=ClientPolicy, description="Tunables applied on the device.")

    @property
    def challenges(self) -> list[str]:
        return [c.strip() for c in self.challenge_pool.split(",") if c.strip() in ALL_CHALLENGES]


SERVER_FIELDS = [name for name in Policy.model_fields if name != "client"]

PRESET_OVERRIDES: dict[str, dict[str, Any]] = {
    "balanced": {},
    "strict": {
        "match_threshold": 0.55,
        "spoof_threshold": 0.60,
        "spoof_hard_floor": 0.35,
        "cvpr_threshold": 0.40,
        "challenge_count": 3,
        "flash_min_correlation": 0.7,
        "turn_strict_direction": True,
        "client": {"parallax_min_shift": 0.10, "smile_threshold": 0.8},
    },
    "relaxed": {
        "match_threshold": 0.40,
        "spoof_hard_floor": 0.20,
        "cvpr_threshold": 0.20,
        "flash_enforce": False,
        "smile_enforce": False,
        "max_challenge_ms": 8000,
        "client": {"challenge_timeout_ms": 15000, "face_lost_grace_ms": 2500, "min_face_width_fraction": 0.2},
    },
    "emulator": {
        "flash_enforce": False,
        "spoof_hard_floor": 0.20,
        "min_face_size": 60,
        "client": {"min_face_width_fraction": 0.2},
    },
}

PRESET_SUMMARY = {
    "balanced": "Calibrated defaults from the environment. Phone-tested attendance check-in.",
    "strict": "Higher match and anti-spoof bars, three challenges, commanded turn direction. Access control, KYC.",
    "relaxed": "Lower bars, flash and smile checks record scores only. Low-risk flows, poor lighting, kiosks.",
    "emulator": "Flash off and smaller faces accepted. Android emulator with a webcam, CI demos.",
}

PRESETS = tuple(PRESET_OVERRIDES)


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out


@lru_cache
def default_policy() -> Policy:
    s = get_settings()
    return Policy(**{name: getattr(s, name) for name in SERVER_FIELDS})


def resolve_policy(preset: str, overrides: dict[str, Any] | str | None) -> Policy:
    if preset not in PRESET_OVERRIDES:
        raise ValueError(f"unknown preset '{preset}', expected one of {', '.join(PRESETS)}")
    patch = json.loads(overrides) if isinstance(overrides, str) else (overrides or {})
    merged = _deep_merge(_deep_merge(default_policy().model_dump(), PRESET_OVERRIDES[preset]), patch)
    return Policy.model_validate(merged)


def preset_policy(preset: str) -> Policy:
    return resolve_policy(preset, None)


class _RequestPolicy:
    __slots__ = ("policy",)

    def __init__(self) -> None:
        self.policy: Policy | None = None


_current: ContextVar[_RequestPolicy | None] = ContextVar("lumiface_policy", default=None)


def get_policy() -> Policy:
    holder = _current.get()
    if holder is not None and holder.policy is not None:
        return holder.policy
    return default_policy()


def use_policy(policy: Policy) -> None:
    """Bind a policy to the current request. Outside a request it binds to the current context."""
    holder = _current.get()
    if holder is None:
        holder = _RequestPolicy()
        _current.set(holder)
    holder.policy = policy


class PolicyScopeMiddleware:
    """Gives every request its own policy slot, shared by the thread-pool contexts FastAPI spawns."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            _current.set(_RequestPolicy())
        await self.app(scope, receive, send)


def policy_schema() -> list[dict[str, Any]]:
    """Flat field list for docs and admin UIs: name, type, default, description."""
    rows = []
    defaults = default_policy()
    for name, f in Policy.model_fields.items():
        if name == "client":
            continue
        rows.append({"name": name, "type": _type_name(f.annotation), "default": getattr(defaults, name),
                     "description": f.description or ""})
    for name, f in ClientPolicy.model_fields.items():
        rows.append({"name": f"client.{name}", "type": _type_name(f.annotation), "default": f.default,
                     "description": f.description or ""})
    return rows


def _type_name(annotation) -> str:
    return getattr(annotation, "__name__", str(annotation))
