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



class ClientPolicy(BaseModel):
    """Tunables the app applies while running the flow. Sent with every session."""

    model_config = ConfigDict(extra="forbid")

    align_hold_ms: int = Field(600, description="Face must stay aligned this long before the first frame.")
    min_face_width_fraction: float = Field(0.28, description="Face box width / frame width lower bound.")
    max_face_width_fraction: float = Field(0.48, description="Face box width / frame width upper bound. Under the face_move start (move_start_max_ratio x the oval), so \"move back\" happens while aligning and the hold before the walk stops the person from backing off further.")
    center_tolerance: float = Field(0.18, description="Allowed offset of the face centre from the frame centre.")
    neutral_max_yaw: float = Field(15, description="Max |yaw| in degrees for a neutral frame.")
    neutral_max_pitch: float = Field(15, description="Max |pitch| in degrees for a neutral frame.")
    challenge_timeout_ms: int = Field(10000, description="Give up on the oval after this long.")
    face_lost_grace_ms: int = Field(1500, description="Fail when no face is seen for this long.")
    oval_min_fill: float = Field(0.85, description="face_move: face width / oval width that counts as fitted (centred within a fifth of the oval).")
    oval_hold_ms: int = Field(500, description="face_move: the face must stay fitted this long.")
    move_start_max_ratio: float = Field(0.8, description="face_move: face width / oval width the challenge must start below, so the move is a real one.")
    settle_after_challenge_ms: int = Field(400, description="Pause after the oval is filled before the flash.")
    settle_after_flash_ms: int = Field(800, description="Pause after the last flash colour before neutral_end.")


class Policy(BaseModel):
    """Everything a project can tune. Field defaults mirror the environment defaults."""

    model_config = ConfigDict(extra="forbid")

    match_threshold: float = Field(description="Min cosine similarity between every frame and the reference photo.")
    consistency_threshold: float = Field(description="Min cosine similarity between two frontal frames.")
    consistency_pose_threshold: float = Field(description="Min similarity when one frame is turned away.")
    pose_frame_max_angle: float = Field(description="|yaw| or |pitch| above this marks a pose frame.")
    spoof_threshold: float = Field(description="MiniFASNet real score, mean over frames.")
    spoof_hard_floor: float = Field(description="MiniFASNet real score every single frame must clear.")
    cvpr_enabled: bool = Field(description="Run the CVPR-2024 ResNet50 gate on a face crop.")
    cvpr_crop_margin: float = Field(description="Face crop margin for the CVPR gate.")
    cvpr_threshold: float = Field(description="CVPR live probability, mean over frames.")
    cvpr_hard_floor: float = Field(description="CVPR live probability every frame must clear.")
    min_face_size: int = Field(description="Min face box side in pixels.")
    reference_max_yaw: float = Field(description="Max |yaw| accepted for a session's reference photo.")
    reference_max_pitch: float = Field(description="Max |pitch| accepted for a session's reference photo.")

    session_ttl_seconds: int = Field(description="A session must be verified within this time.")
    allow_browser_api_key: bool = Field(description="Accept the project key from a browser origin other than localhost. Development only.")
    oval_width_fraction: float = Field(description="face_move: oval width as a fraction of the frame's shorter side; the face must fill it.")
    oval_center_y: float = Field(description="face_move: oval centre as a fraction of the frame height.")
    oval_height_ratio: float = Field(description="face_move: oval height / width.")
    move_min_growth: float = Field(description="face_move: face width at the end / at the start of the window, server-side.")
    move_min_fill: float = Field(description="face_move: face width at the end / oval width, server-side. Below the device's oval_min_fill: the server's box is a little smaller and the person stops the moment the device says hold.")
    min_challenge_ms: int = Field(description="Shortest accepted face_move window.")
    max_challenge_ms: int = Field(description="Longest accepted face_move window.")
    min_session_ms: int = Field(description="Shortest accepted whole session.")

    flash_count: int = Field(description="Screen-flash colours per session; 0 disables.")
    flash_enforce: bool = Field(description="Reject on flash failure; false records scores only.")
    flash_min_correlation: float = Field(description="Min correlation between commanded and seen colour sequence.")
    flash_min_response: float = Field(description="Min RMS chroma change on the face, 8-bit units.")
    flash_max_background_ratio: float = Field(description="Max surroundings/face flash response.")
    flash_hold_ms: int = Field(description="How long the app shows each colour.")

    client: ClientPolicy = Field(default_factory=ClientPolicy, description="Tunables applied on the device.")

SERVER_FIELDS = [name for name in Policy.model_fields if name != "client"]

PRESET_OVERRIDES: dict[str, dict[str, Any]] = {
    "balanced": {},
    "strict": {
        "match_threshold": 0.55,
        "spoof_threshold": 0.60,
        "spoof_hard_floor": 0.35,
        "cvpr_threshold": 0.40,
        "move_min_growth": 1.4,
        "flash_min_correlation": 0.7,
        "client": {"oval_min_fill": 0.9, "move_start_max_ratio": 0.5},
    },
    "relaxed": {
        "match_threshold": 0.40,
        "spoof_hard_floor": 0.20,
        "cvpr_threshold": 0.20,
        "flash_enforce": False,
        "max_challenge_ms": 15000,
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
    "balanced": "Calibrated defaults from the environment: move into the oval, then the flash. Phone-tested attendance check-in.",
    "strict": "Higher match and anti-spoof bars, a longer walk into a fuller oval, tighter flash correlation. Access control, KYC.",
    "relaxed": "Lower bars, the flash records scores only, more time for the oval. Low-risk flows, poor lighting, kiosks.",
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
