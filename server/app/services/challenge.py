"""The plan the server hands the device: one challenge, the oval, plus the flash colours chosen elsewhere."""
from __future__ import annotations

from ..policy import get_policy

ALL_CHALLENGES = ("face_move",)


def new_challenges() -> list[str]:
    return ["face_move"]


def oval_for(challenges: list[str]) -> dict | None:
    """The oval a face_move challenge asks the face to fill: `cx`, `cy` are fractions of the frame,
    `width` a fraction of the frame's shorter side (faces scale with it whatever the orientation),
    `height_ratio` the oval's height over its width."""
    if "face_move" not in challenges:
        return None
    s = get_policy()
    return {"cx": 0.5, "cy": s.oval_center_y, "width": s.oval_width_fraction, "height_ratio": s.oval_height_ratio}
