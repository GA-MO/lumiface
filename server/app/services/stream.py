"""Streamed verification: the device sends frames continuously over a WebSocket while it runs
the plan the server handed it; the server stamps every frame and event with its own clock and
decides everything from what it received.

The device's events (`aligned`, `challenge_done`, `flash`, `flash_end`, `end`) only tell the
server *where to look*. Whether the face really moved into the oval or a colour reflection
actually happened is read off the server's own face boxes and pixels inside those windows, and
every duration is measured on the server's clock, so a scripted client gains nothing by lying
about its timestamps.

    align window   frames before `aligned`             -> neutral baseline, spoof, embedding
    challenge 0    (aligned, challenge_done_0]          -> the face box grew from far into the oval
    flash i        [flash_i, flash_i+1 or flash_end)    -> face-patch colour under colour i
    end window     after flash_end (or last challenge)  -> neutral again, spoof, embedding, consistency

Every gate runs whatever the ones before it found (`details["gates"]` holds each verdict in
pipeline order); the reason code is the first gate that failed and counts.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass

import numpy as np

from ..policy import get_policy
from .antispoof import get_antispoof
from .face import BadImage, FaceResult, cosine, decode_image, get_face_engine
from .flash import face_patch_mean_rgb, flash_passes, score_flash, surroundings_mean_rgb
from .verify import VerifyResult, _consistency, _single_face

FLASH_LATENCY_MS = 120  # the screen needs a moment to show a colour before the camera sees it
MAX_FRAMES_PER_WINDOW = 16  # the detector runs on at most this many frames of a window


@dataclass
class StreamFrame:
    recv_ms: int
    client_ms: int
    data: bytes


@dataclass
class StreamEvent:
    name: str  # aligned | challenge_done | flash | flash_end | end
    recv_ms: int
    index: int | None = None
    client_ms: int | None = None


@dataclass
class Windows:
    align: tuple[int, int]
    challenges: list[tuple[int, int]]
    flashes: list[tuple[int, int]]
    end: tuple[int, int]


@dataclass
class Analysed:
    frame: StreamFrame
    face: FaceResult | None
    error: str | None = None
    img: np.ndarray | None = None


def movement_observed(seen: list[Analysed], s) -> tuple[bool, dict, Analysed]:
    """The face_move challenge as the server sees it: over the window the face box grew from far to
    filling the oval, the way a head moving towards the camera does. `seen` is in time order; the
    last frames give the end and the closest of them is the key frame; the start is the farthest the
    face was before that, because the window opens at `aligned` and a person who aligned close first
    backs off on the device's "move back" and only then walks in."""
    def width_fraction(a: Analysed) -> float:
        # Faces scale with the frame's shorter side: the width of a portrait phone frame, the height
        # of a landscape webcam frame. The oval is sized in the same unit.
        return float(a.face.bbox[2] - a.face.bbox[0]) / max(min(a.img.shape[0], a.img.shape[1]), 1)

    def centre_x(a: Analysed) -> float:
        return float(a.face.bbox[0] + a.face.bbox[2]) / 2 / max(a.img.shape[1], 1)

    widths = [width_fraction(a) for a in seen]
    tail_from = max(len(seen) - 3, 0)
    peak_at = tail_from + max(range(tail_from, len(seen)), key=lambda i: widths[i]) - tail_from
    peak, end = seen[peak_at], widths[peak_at]
    start = min(widths[:max(peak_at, 1)])
    fill = end / max(s.oval_width_fraction, 1e-3)
    growth = end / max(start, 1e-3)
    centred = abs(centre_x(peak) - 0.5) <= 0.2
    info = {"start_width": round(start, 3), "end_width": round(end, 3), "growth": round(growth, 2),
            "fill": round(fill, 2), "centred": centred}
    return growth >= s.move_min_growth and fill >= s.move_min_fill and centred, info, peak


def build_windows(events: list[StreamEvent], first_frame_ms: int, challenges: list[str],
                  flash_colors: list[str]) -> Windows | str:
    """Server-clock windows from the device's events, or a reason code when the sequence is not
    the one the plan asked for."""
    expected = ["aligned", *["challenge_done"] * len(challenges), *["flash"] * len(flash_colors),
                *(["flash_end"] if flash_colors else []), "end"]
    names = [e.name for e in events]
    if names != expected:
        return "TIMING_ORDER"
    for i, e in enumerate(events):
        if e.name in ("challenge_done", "flash") and e.index != names[:i].count(e.name):
            return "TIMING_ORDER"
    ts = [e.recv_ms for e in events]
    if any(b < a for a, b in zip(ts, ts[1:])):
        return "TIMING_ORDER"
    aligned = events[0].recv_ms
    challenge_windows, boundary = [], aligned
    for e in events[1:1 + len(challenges)]:
        challenge_windows.append((boundary, e.recv_ms))
        boundary = e.recv_ms
    flash_events = events[1 + len(challenges):1 + len(challenges) + len(flash_colors)]
    flash_windows = []
    if flash_colors:
        flash_end = events[-2].recv_ms
        for i, e in enumerate(flash_events):
            nxt = flash_events[i + 1].recv_ms if i + 1 < len(flash_events) else flash_end
            flash_windows.append((e.recv_ms + FLASH_LATENCY_MS, nxt))
        boundary = flash_end
    return Windows(align=(first_frame_ms, aligned), challenges=challenge_windows, flashes=flash_windows,
                   end=(boundary, events[-1].recv_ms))


def placement_windows(frames: list[StreamFrame], events: list[StreamEvent], challenges: list[str],
                      flash_colors: list[str], server: Windows) -> Windows:
    """Where each frame belongs, on the device's capture clock. A phone encodes and uploads a frame
    hundreds of ms after the camera saw it while an event is a few bytes, so by server arrival a
    frame taken under colour 0 lands in colour 1's window and a blink's reopening lands after
    `challenge_done`. Durations stay on the server clock; only membership uses the device stamps,
    and only when every event but `end` carries one, in order (older clients keep the server clock).
    A client that lies about its stamps still has to show the right colours in the right windows."""
    stamped = [e for e in events if e.name != "end"]
    if not frames or any(e.client_ms is None for e in stamped):
        return server
    ts = [e.client_ms for e in stamped]
    if any(b < a for a, b in zip(ts, ts[1:])):
        return server
    last = max(f.client_ms for f in frames)
    shadow = [StreamEvent(e.name, e.client_ms if e.client_ms is not None else last, e.index) for e in events]
    w = build_windows(shadow, min(f.client_ms for f in frames), challenges, flash_colors)
    return server if isinstance(w, str) else w


def _in(frames: list[StreamFrame], window: tuple[int, int], by_client: bool = False) -> list[StreamFrame]:
    lo, hi = window
    return [f for f in frames if lo <= (f.client_ms if by_client else f.recv_ms) <= hi]


def _sample(frames: list[StreamFrame], n: int = MAX_FRAMES_PER_WINDOW) -> list[StreamFrame]:
    if len(frames) <= n:
        return frames
    idx = np.linspace(0, len(frames) - 1, n).round().astype(int)
    return [frames[i] for i in dict.fromkeys(idx)]


class _Analyser:
    """Runs the detector once per frame and remembers the result."""

    def __init__(self) -> None:
        self.cache: dict[int, Analysed] = {}
        self.engine = get_face_engine()

    def __call__(self, f: StreamFrame) -> Analysed:
        if id(f) in self.cache:
            return self.cache[id(f)]
        try:
            img = decode_image(f.data)
        except BadImage:
            a = Analysed(f, None, "BAD_IMAGE")
        else:
            face, err = _single_face(img)
            a = Analysed(f, face, err, img)
        self.cache[id(f)] = a
        return a


def _with_face(analyser: _Analyser, frames: list[StreamFrame]) -> list[Analysed]:
    return [a for a in (analyser(f) for f in frames) if a.face is not None]


class _Gates:
    """The verdict of every gate in pipeline order. Each gate runs whatever the ones before it said,
    so a session refused at the flash still carries its spoof and match scores for the backend; the
    first gate that failed and counts gives the reason code, and only its extras land in `details`."""

    def __init__(self, details: dict) -> None:
        self.details = details
        self.table: dict[str, str] = details.setdefault("gates", {})
        self.reason: str | None = None

    def record(self, name: str, reason: str | None = None, counts: bool = True, **extra) -> None:
        self.table[name] = reason or "pass"
        if reason and counts and self.reason is None:
            self.reason = reason
            self.details.update(extra)

    def skip(self, name: str) -> None:
        self.table[name] = "skipped"


def analyze_stream(frames: list[StreamFrame], events: list[StreamEvent], challenges: list[str],
                   flash_colors: list[str], enrolled: np.ndarray | None) -> VerifyResult:
    s = get_policy()
    if not frames:
        return VerifyResult(False, "FRAME_COUNT", details={"gates": {"frames": "FRAME_COUNT"}})
    frames = sorted(frames, key=lambda f: f.recv_ms)
    windows = build_windows(events, frames[0].recv_ms, challenges, flash_colors)
    if isinstance(windows, str):
        return VerifyResult(False, windows, details={"frames": len(frames), "gates": {"frames": "pass", "order": windows}})

    details: dict = {"gates": {"frames": "pass", "order": "pass"}, "frames": len(frames), "windows": {
        "align_ms": windows.align[1] - windows.align[0],
        "challenges_ms": [b - a for a, b in windows.challenges],
        "flash_ms": [b - a for a, b in windows.flashes],
        "end_ms": windows.end[1] - windows.end[0],
    }}
    g = _Gates(details)

    # Server-clock timing: the session and every challenge took a plausible amount of real time.
    timing = None
    total = windows.end[1] - windows.align[1]
    if total < s.min_session_ms:
        timing = "TIMING_TOO_FAST"
    for a, b in windows.challenges:
        if timing is None and b - a < s.min_challenge_ms:
            timing = "TIMING_TOO_FAST"
        if timing is None and b - a > s.max_challenge_ms:
            timing = "TIMING_TOO_SLOW"
    g.record("timing", timing)

    # A replayed still or a frozen feed sends the same bytes again and again.
    digests = {hashlib.blake2b(f.data, digest_size=8).digest() for f in frames}
    details["unique_frames"] = len(digests)
    static = len(frames) >= 8 and len(digests) < max(4, len(frames) // 2)
    g.record("static", "FRAMES_STATIC" if static else None)

    place = placement_windows(frames, events, challenges, flash_colors, windows)
    by_client = place is not windows
    details["placement"] = "client" if by_client else "server"

    analyser = _Analyser()
    per_frame: list[dict] = []
    key_faces: list[Analysed] = []

    def note(kind: str, a: Analysed) -> None:
        per_frame.append({"kind": kind, "t": a.frame.recv_ms - frames[0].recv_ms, "yaw": round(a.face.yaw, 1),
                          "pitch": round(a.face.pitch, 1), "det": round(a.face.det_score, 3)})
        key_faces.append(a)

    # Neutral baseline: the last frames of the align window, when the device said the face was set.
    baseline = _with_face(analyser, _sample(_in(frames, place.align, by_client))[-3:])
    if baseline:
        note("neutral_start", baseline[-1])
    g.record("neutral_start", None if baseline else "NO_FACE", window="align")

    # The challenge: the face box read off the server's own detector inside the window.
    for i, (ch, window) in enumerate(zip(challenges, place.challenges)):
        name = f"challenge_{i}"
        seen = _with_face(analyser, _sample(_in(frames, window, by_client), MAX_FRAMES_PER_WINDOW))
        if not seen:
            g.record(name, "NO_FACE", window=name)
            continue
        ok, info, peak = movement_observed(seen, s)
        details[name] = {"name": ch, "frames": len(seen), **info}
        g.record(name, None if ok else "MOVEMENT_MISMATCH", challenge=ch)
        note(name, peak)

    # Flash: the colour on the face during each colour's window, with the box from a frame in it.
    if flash_colors:
        observed, background = [], []
        last_box = key_faces[-1].face.bbox if key_faces else None
        for i, window in enumerate(place.flashes):
            fw = _in(frames, window, by_client)
            mid = analyser(fw[len(fw) // 2]) if fw else None
            if mid is not None and mid.face is not None:
                last_box = mid.face.bbox
            if not fw or last_box is None:
                details["flash"] = {"window": f"flash_{i}", "reason": "no frames" if not fw else "no face",
                                    "enforced": s.flash_enforce}
                observed = []
                break
            patches, rings = [], []
            for f in fw:
                cached = analyser.cache.get(id(f))
                img = cached.img if cached is not None else None
                if img is None:
                    try:
                        img = decode_image(f.data)
                    except BadImage:
                        continue
                patches.append(face_patch_mean_rgb(img, last_box))
                rings.append(surroundings_mean_rgb(img, last_box))
            observed.append(np.mean(patches, axis=0))
            background.append(np.mean(rings, axis=0))
        passed = False
        if observed:
            fr = score_flash(observed, flash_colors, background)
            details["flash"] = {"correlation": round(fr.correlation, 3), "response": round(fr.response, 2),
                                "order_ok": fr.order_ok, "deltas": fr.per_frame,
                                "background_ratio": None if fr.background_ratio is None else round(fr.background_ratio, 2),
                                "enforced": s.flash_enforce}
            passed = flash_passes(fr)
        g.record("flash", None if passed else "FLASH_FAIL", counts=s.flash_enforce)

    # Neutral again at the end.
    ending = _with_face(analyser, _sample(_in(frames, place.end, by_client))[-3:])
    if ending:
        note("neutral_end", ending[-1])
    g.record("neutral_end", None if ending else "NO_FACE", window="end")

    # Passive anti-spoof on the key frames, then identity and consistency, as before.
    spoof_mean = match_min = consistency = None
    if key_faces:
        spoof_scores, cvpr_scores = [], []
        for row, a in zip(per_frame, key_faces):
            sp = get_antispoof().score(a.img, a.face.bbox)
            spoof_scores.append(sp.real)
            row["spoof"] = round(sp.real, 4)
            if sp.cvpr is not None:
                cvpr_scores.append(sp.cvpr)
                row["cvpr"] = round(sp.cvpr, 4)
        spoof_mean = float(np.mean(spoof_scores))
        low = spoof_mean < s.spoof_threshold or min(spoof_scores) < s.spoof_hard_floor
        g.record("minifasnet", "SPOOF" if low else None, gate="minifasnet")
        if cvpr_scores:
            cvpr_mean = float(np.mean(cvpr_scores))
            details["cvpr_mean"] = round(cvpr_mean, 4)
            low = cvpr_mean < s.cvpr_threshold or min(cvpr_scores) < s.cvpr_hard_floor
            g.record("cvpr2024", "SPOOF" if low else None, gate="cvpr2024")
        else:
            g.skip("cvpr2024")
    else:
        g.skip("minifasnet")
        g.skip("cvpr2024")
    details["key_frames"] = per_frame

    faces = [a.face for a in key_faces]
    if enrolled is not None and faces:
        match_scores = [cosine(f.embedding, enrolled) for f in faces]
        match_min = float(min(match_scores))
        details["match"] = [round(m, 4) for m in match_scores]
        g.record("match", "NO_MATCH" if match_min < s.match_threshold else None)
    else:
        g.skip("match")

    if faces:
        consistency, consistent = _consistency(faces)
        details["consistency"] = round(consistency, 4)
        g.record("consistency", None if consistent else "INCONSISTENT")
    else:
        g.skip("consistency")

    return VerifyResult(g.reason is None, g.reason or "OK", match_score=match_min, spoof_score=spoof_mean,
                        consistency_score=consistency, details=details)
