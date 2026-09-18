from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/facegate.db"
    bootstrap_project_name: str = "default"
    bootstrap_api_key: str | None = None
    bootstrap_preset: str = "balanced"
    admin_api_key: str | None = None
    debug: bool = False

    weights_dir: str = "weights"
    det_size: int = 640
    store_frames: bool = False
    frames_dir: str = "data/frames"

    match_threshold: float = 0.45
    consistency_threshold: float = 0.60
    consistency_pose_threshold: float = 0.40
    pose_frame_max_angle: float = 20.0
    spoof_threshold: float = 0.50
    spoof_hard_floor: float = 0.30
    cvpr_enabled: bool = True
    cvpr_crop_margin: float = 0.30
    cvpr_threshold: float = 0.30
    cvpr_hard_floor: float = 0.05
    min_face_size: int = 112
    enroll_max_yaw: float = 20.0
    enroll_max_pitch: float = 20.0
    turn_min_yaw: float = 20.0
    nod_min_pitch: float = 15.0
    turn_strict_direction: bool = False
    smile_enforce: bool = True
    smile_min_width_gain: float = 1.08
    smile_min_lift: float = 0.04

    session_ttl_seconds: int = 60
    challenge_count: int = 2
    challenge_pool: str = "blink,turn_left,turn_right,smile,nod"
    required_challenge: str = "smile"
    min_challenge_ms: int = 300
    max_challenge_ms: int = 5000
    min_session_ms: int = 1500

    flash_count: int = 3
    flash_enforce: bool = True
    flash_min_correlation: float = 0.5
    flash_min_response: float = 2.0
    flash_max_background_ratio: float = 0.8
    flash_hold_ms: int = 450


@lru_cache
def get_settings() -> Settings:
    return Settings()
