from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/face_checkin.db"
    bootstrap_project_name: str = "default"
    bootstrap_api_key: str | None = None
    debug: bool = False

    weights_dir: str = "weights"
    det_size: int = 640

    # thresholds (calibrate with scripts/calibrate.py)
    match_threshold: float = 0.45
    consistency_threshold: float = 0.60
    spoof_threshold: float = 0.50   # MiniFASNet ensemble, mean over frames
    spoof_hard_floor: float = 0.30  # MiniFASNet, every frame
    cvpr_enabled: bool = True       # CVPR-2024 ResNet50 on a face crop (catches bezel-free screen replay)
    cvpr_crop_margin: float = 0.30  # face box margin; 0.2 false-rejects genuine phone video, >=0.4 lets bezel-free replay through
    cvpr_threshold: float = 0.30    # mean over frames (live prob); at margin 0.3: replay <= 0.015, genuine >= 0.30 (2026-09-17)
    cvpr_hard_floor: float = 0.05   # every frame
    min_face_size: int = 112
    enroll_max_yaw: float = 20.0
    enroll_max_pitch: float = 20.0
    turn_min_yaw: float = 20.0
    nod_min_pitch: float = 15.0
    turn_strict_direction: bool = False

    # session / timing
    session_ttl_seconds: int = 60
    challenge_count: int = 2
    challenge_pool: str = "blink,turn_left,turn_right,smile,nod"
    min_challenge_ms: int = 300
    max_challenge_ms: int = 5000  # human reaction to a prompt; replayed video responds at random times
    min_session_ms: int = 1500

    store_frames: bool = False
    frames_dir: str = "data/frames"

    @property
    def challenges(self) -> list[str]:
        return [c.strip() for c in self.challenge_pool.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
