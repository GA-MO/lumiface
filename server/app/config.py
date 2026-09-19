from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/lumiface.db"
    bootstrap_project_name: str = "default"
    bootstrap_api_key: str | None = None
    bootstrap_preset: str = "balanced"
    admin_api_key: str | None = None
    debug: bool = False

    weights_dir: str = "weights"
    det_size: int = 640
    max_upload_bytes: int = 32 * 1024 * 1024  # whole request body
    max_frame_bytes: int = 4 * 1024 * 1024  # one JPEG
    max_image_pixels: int = 20_000_000
    max_stream_frames: int = 900  # frames the pipeline keeps: ~10 fps of JPEG, or a video thinned to this
    max_stream_chunks: int = 1800  # messages accepted on the stream: JPEG frames, or video chunks
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
    reference_max_yaw: float = 20.0
    reference_max_pitch: float = 20.0

    session_ttl_seconds: int = 60
    allow_browser_api_key: bool = False
    retention_interval_seconds: int = 300
    session_purge_grace_seconds: int = 3600
    oval_width_fraction: float = 0.62
    oval_center_y: float = 0.45
    oval_height_ratio: float = 1.35
    move_min_growth: float = 1.15
    move_min_fill: float = 0.75
    min_challenge_ms: int = 300
    max_challenge_ms: int = 10000
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
