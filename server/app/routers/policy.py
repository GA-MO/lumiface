import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ValidationError
from sqlmodel import Session

from ..db import get_db
from ..deps import current_project, project_policy
from ..models import Project
from ..policy import PRESET_OVERRIDES, PRESET_SUMMARY, PRESETS, Policy, policy_schema, preset_policy, resolve_policy

router = APIRouter(prefix="/v1/policy", tags=["policy"])


class PolicyOut(BaseModel):
    project: str
    preset: str
    overrides: dict[str, Any]
    effective: Policy


class PolicyUpdate(BaseModel):
    preset: str | None = None
    overrides: dict[str, Any] | None = None
    merge: bool = True


class PresetOut(BaseModel):
    name: str
    summary: str
    overrides: dict[str, Any]
    effective: Policy


def _out(project: Project) -> PolicyOut:
    return PolicyOut(project=project.name, preset=project.preset, overrides=json.loads(project.policy_overrides),
                     effective=project_policy(project))


@router.get("", response_model=PolicyOut)
def get_policy_route(project: Project = Depends(current_project)):
    return _out(project)


@router.put("", response_model=PolicyOut)
def update_policy(body: PolicyUpdate, project: Project = Depends(current_project),
                  db: Session = Depends(get_db)):
    preset = body.preset or project.preset
    if preset not in PRESETS:
        raise HTTPException(422, {"reason_code": "UNKNOWN_PRESET", "presets": list(PRESETS)})
    current = json.loads(project.policy_overrides)
    if body.overrides is None:
        overrides = current if body.merge else {}
    else:
        overrides = _deep_merge(current, body.overrides) if body.merge else body.overrides
    try:
        resolve_policy(preset, overrides)
    except ValidationError as e:
        raise HTTPException(422, {"reason_code": "POLICY_INVALID", "errors": e.errors(include_url=False)})
    project.preset = preset
    project.policy_overrides = json.dumps(overrides)
    db.add(project)
    db.commit()
    db.refresh(project)
    return _out(project)


@router.delete("", response_model=PolicyOut)
def reset_policy_route(project: Project = Depends(current_project), db: Session = Depends(get_db)):
    project.preset = "balanced"
    project.policy_overrides = "{}"
    db.add(project)
    db.commit()
    db.refresh(project)
    return _out(project)


@router.get("/presets", response_model=list[PresetOut])
def list_presets(_: Project = Depends(current_project)):
    return [PresetOut(name=p, summary=PRESET_SUMMARY[p], overrides=PRESET_OVERRIDES[p], effective=preset_policy(p))
            for p in PRESETS]


@router.get("/schema")
def get_schema(_: Project = Depends(current_project)):
    return policy_schema()


def _deep_merge(base: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for k, v in patch.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _deep_merge(out[k], v)
        else:
            out[k] = v
    return out
