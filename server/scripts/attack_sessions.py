"""Play a stored genuine session back at a live server the way an attacker without a face would.

    STORE_FRAMES=1 DEBUG=1 uv run uvicorn app.main:app --port 8000        # in another terminal
    uv run python scripts/attack_sessions.py data/sessions/genuine/<session> --kind injection photo static

Each kind is one verification session, stored under `data/frames/<project>/` like a live one, so it
can be copied into `data/sessions/attack/` and replayed:

    injection   the recording's own frames and events at their own cadence (a virtual camera feeding
                a recorded video; the flash colours on the face are the ones the recording saw)
    photo       one far frame of the recording, scaled towards the camera over the challenge window
                the way a printout moved in is, then held through the flash and the end
    static      the same printout held still from start to end

Frames go as JPEG with the recording's device stamps; every frame gets sensor-like noise so the
bytes never repeat, as a camera's never do.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import json
import sys
import time
from pathlib import Path

import cv2
import httpx
import numpy as np
import websockets

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.replay_sessions import load  # noqa: E402


def noisy(img: np.ndarray, rng: np.random.Generator) -> bytes:
    noise = rng.normal(0, 2, img.shape).astype(np.float32)
    out = np.clip(img.astype(np.float32) + noise, 0, 255).astype(np.uint8)
    return cv2.imencode(".jpg", out, [cv2.IMWRITE_JPEG_QUALITY, 85])[1].tobytes()


def zoomed(img: np.ndarray, scale: float) -> np.ndarray:
    """The centre of the image enlarged by `scale` (a printout brought closer to the camera)."""
    h, w = img.shape[:2]
    cw, ch = int(w / scale), int(h / scale)
    x0, y0 = (w - cw) // 2, (h - ch) // 2
    return cv2.resize(img[y0:y0 + ch, x0:x0 + cw], (w, h), interpolation=cv2.INTER_LINEAR)


def build(kind: str, frames, events, rng: np.random.Generator) -> list[tuple[int, bytes]]:
    """(device_ms, jpeg) per frame, on the recording's device clock."""
    if kind == "injection":
        return [(f.client_ms, noisy(cv2.imdecode(np.frombuffer(f.data, np.uint8), cv2.IMREAD_COLOR), rng)) for f in frames]
    aligned = next(e.client_ms for e in events if e.name == "aligned")
    done = next(e.client_ms for e in events if e.name == "challenge_done")
    # The printout is the frame the recording had when the device said "aligned": the far position.
    far_frame = min(frames, key=lambda f: abs(f.client_ms - aligned))
    far = cv2.imdecode(np.frombuffer(far_frame.data, np.uint8), cv2.IMREAD_COLOR)
    out = []
    for f in frames:
        scale = 1.0
        if kind == "photo" and f.client_ms > aligned:
            scale = 1.0 + 0.7 * min(max((f.client_ms - aligned) / max(done - aligned, 1), 0.0), 1.0)
        out.append((f.client_ms, noisy(zoomed(far, scale) if scale > 1.0 else far, rng)))
    return out


async def play(url: str, key: str, reference: Path | None, kind: str, folder: Path) -> dict:
    frames, events, meta = load(folder)
    rng = np.random.default_rng(len(kind))
    payloads = build(kind, frames, events, rng)
    async with httpx.AsyncClient(base_url=url, headers={"X-API-Key": key}) as http:
        body = {"reference_photo": base64.b64encode(reference.read_bytes()).decode()} if reference else {}
        sess = (await http.post("/v1/sessions", json=body)).raise_for_status().json()
    ws_url = url.replace("http", "ws", 1) + f"/v1/sessions/{sess['session_id']}/stream"
    async with websockets.connect(ws_url, max_size=None) as ws:
        await ws.send(json.dumps({"type": "hello", "token": sess["session_token"], "format": "jpeg",
                                  "client": {"platform": "attack", "sdk": f"attack_sessions/{kind}"}}))
        await ws.recv()
        timeline = [(t, ("frame", data)) for t, data in payloads]
        timeline += [(e.client_ms, ("event", e)) for e in events if e.name != "end" and e.client_ms is not None]
        timeline.sort(key=lambda x: x[0])
        t0, start = timeline[0][0], time.monotonic()
        for t, (what, item) in timeline:
            wait = (t - t0) / 1000 - (time.monotonic() - start)
            if wait > 0:
                await asyncio.sleep(wait)
            if what == "frame":
                await ws.send(t.to_bytes(8, "big") + item)
            else:
                ev = {"type": "event", "name": item.name, "ts": t}
                if item.index is not None:
                    ev["index"] = item.index
                await ws.send(json.dumps(ev))
        await ws.send(json.dumps({"type": "end"}))
        result = json.loads(await ws.recv())
    return {"session_id": sess["session_id"], **result}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("session", type=Path, help="a stored genuine session folder")
    ap.add_argument("--kind", nargs="+", default=["injection", "photo", "static"], choices=["injection", "photo", "static"])
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--key", default="change-me")
    ap.add_argument("--reference", type=Path, help="photo of the victim to claim as reference_photo; omitted = liveness session")
    args = ap.parse_args()
    for kind in args.kind:
        r = asyncio.run(play(args.url, args.key, args.reference, kind, args.session))
        print(f"{kind:10} {r['session_id'][:8]}  {r.get('reason_code')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
