"""Calibration helper, only mounted when DEBUG=1."""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from ..deps import current_project
from ..services.antispoof import get_antispoof
from ..services.face import decode_image, get_face_engine

router = APIRouter(prefix="/v1/debug", tags=["debug"])


class FaceScore(BaseModel):
    bbox: list[float]
    det_score: float
    yaw: float
    pitch: float
    roll: float
    spoof_real: float
    spoof_per_model: dict[str, float]
    cvpr_live: float | None
    embedding: list[float]


@router.post("/score", response_model=list[FaceScore])
async def score(photo: UploadFile = File(...), _=Depends(current_project)):
    img = decode_image(await photo.read())
    faces = get_face_engine().analyze(img)
    if not faces:
        raise HTTPException(422, {"reason_code": "NO_FACE"})
    out = []
    for f in faces:
        sp = get_antispoof().score(img, f.bbox)
        out.append(FaceScore(bbox=[float(v) for v in f.bbox], det_score=f.det_score, yaw=f.yaw, pitch=f.pitch,
                             roll=f.roll, spoof_real=sp.real, spoof_per_model=sp.per_model, cvpr_live=sp.cvpr,
                             embedding=f.embedding.tolist()))
    return out
