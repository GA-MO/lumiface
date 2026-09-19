"""Re-run the verify pipeline over sessions the server stored with STORE_FRAMES=1.

    uv run python scripts/replay_sessions.py data/frames/1                 # every session under it
    uv run python scripts/replay_sessions.py data/frames/1/<session> ...   # some of them
    uv run python scripts/replay_sessions.py data/frames/1 --expect ok=6 replay=0

Each session folder holds the frames and a `session.json` (plan, both clocks, subject, verdict).
The pipeline runs exactly as in the WebSocket handler, with the policy from the environment
(`FLASH_ENFORCE=0 uv run python scripts/replay_sessions.py …` to try a change), and the subject's
embedding from the database (or `--enrol photo.jpg`). The last column compares with the verdict the
session got when it was live, so a pipeline change shows up as a diff instead of another round in
front of a camera; the line under it is every gate's own verdict, since each gate runs whatever the
ones before it said. Folders without `session.json` (older stores) are replayed on the server clock.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.stream import StreamEvent, StreamFrame, analyze_stream  # noqa: E402


def load(folder: Path) -> tuple[list[StreamFrame], list[StreamEvent], dict]:
    meta_path = folder / "session.json"
    if meta_path.exists():
        meta = json.loads(meta_path.read_text())
        frames = [StreamFrame(recv_ms=f["recv_ms"], client_ms=f["client_ms"], data=(folder / f["file"]).read_bytes())
                  for f in meta["frames"]]
        events = [StreamEvent(name=e["name"], recv_ms=e["recv_ms"], index=e["index"], client_ms=e["client_ms"])
                  for e in meta["events"]]
        return frames, events, meta
    events_path = folder / "events.json"
    if not events_path.exists():
        raise FileNotFoundError(f"{folder}: no session.json or events.json")
    frames = []
    for jpg in sorted(folder.glob("*.jpg")):
        t = int(jpg.stem.split("_")[1])
        frames.append(StreamFrame(recv_ms=t, client_ms=t, data=jpg.read_bytes()))
    events = [StreamEvent(name=e["name"], recv_ms=e["t"], index=e["index"]) for e in json.loads(events_path.read_text())]
    return frames, events, {}


def enrolled_embedding(subject_id: str | None, photo: Path | None, session_dir: Path | None = None) -> np.ndarray | None:
    """The photo given, else `<set>/subjects/<id>.npy` next to a labelled set, else the database."""
    if session_dir is not None and subject_id:
        for base in (session_dir.parent.parent, session_dir.parent):
            npy = base / "subjects" / f"{subject_id}.npy"
            if npy.exists():
                return np.load(npy)
    if photo is not None:
        from app.services.face import decode_image, get_face_engine
        faces = get_face_engine().analyze(decode_image(photo.read_bytes()))
        return faces[0].embedding if faces else None
    if not subject_id:
        return None
    from sqlmodel import Session, select

    from app.db import get_engine
    from app.models import Subject
    with Session(get_engine()) as db:
        row = db.exec(select(Subject).where(Subject.external_id == subject_id)).first()
        return np.frombuffer(row.embedding, dtype=np.float32) if row else None


def gate_line(details: dict) -> str:
    """One word per gate: `ok`, `-` (skipped) or the reason code; a flash that was not enforced is `(shadow)`."""
    words = []
    for name, verdict in details.get("gates", {}).items():
        word = {"pass": "ok", "skipped": "-"}.get(verdict, verdict)
        if name == "flash" and verdict != "pass" and not details.get("flash", {}).get("enforced", True):
            word += "(shadow)"
        words.append(f"{name}={word}")
    return " ".join(words)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("paths", nargs="+", type=Path, help="session folders, or a folder of them")
    ap.add_argument("--enrol", type=Path, help="photo to enrol instead of the subject in the database")
    ap.add_argument("--details", action="store_true", help="print the pipeline details of every session")
    args = ap.parse_args()

    folders: list[Path] = []
    for p in args.paths:
        if (p / "session.json").exists() or (p / "events.json").exists():
            folders.append(p)
        else:
            folders += sorted(d for d in p.iterdir() if d.is_dir() and ((d / "session.json").exists() or (d / "events.json").exists()))
    if not folders:
        print("no sessions found", file=sys.stderr)
        return 2

    embeddings: dict[str | None, np.ndarray | None] = {}
    changed = 0
    for folder in folders:
        frames, events, meta = load(folder)
        if not meta:
            print(f"{folder.name[:8]}  (no session.json: cannot replay without the plan)")
            continue
        subject_id = meta.get("subject_id")
        if subject_id not in embeddings:
            embeddings[subject_id] = enrolled_embedding(subject_id, args.enrol, folder)
        result = analyze_stream(frames, events, meta["challenges"], meta["flash_colors"], embeddings[subject_id])
        was = meta.get("verdict", {}).get("reason_code")
        mark = "=" if was == result.reason_code else "≠"
        if mark == "≠":
            changed += 1
        client = meta.get("client", {})
        print(f"{folder.name[:8]}  {client.get('platform', '?'):7} {','.join(meta['challenges']):22} "
              f"now {result.reason_code:20} was {was or '-':20} {mark}")
        print("    " + gate_line(result.details))
        if args.details:
            print("   ", json.dumps({k: v for k, v in result.details.items() if k != "key_frames"})[:600])
    print(f"{len(folders)} sessions, {changed} changed verdict")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
