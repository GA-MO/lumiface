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
    consistency_threshold: float = 0.60       # between frontal frames
    consistency_pose_threshold: float = 0.40  # frames taken mid turn/nod (Galaxy S25+ nod at -40° pitch: 0.47-0.55)
    pose_frame_max_angle: float = 20.0        # |yaw| or |pitch| above this = pose frame
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
    # smile re-check on the server from 68 landmarks (services/expression.py); either test passing is enough
    smile_enforce: bool = True
    smile_min_width_gain: float = 1.08  # mouth width vs neutral frame; genuine smiles measured 1.14-1.16
    smile_min_lift: float = 0.04        # corner lift vs neutral frame (inter-ocular units); genuine 0.068-0.071

    # session / timing
    session_ttl_seconds: int = 60
    challenge_count: int = 2
    challenge_pool: str = "blink,turn_left,turn_right,smile,nod"
    required_challenge: str = "smile"  # always in the picked set (latex/silicone masks pass passive gates)
    min_challenge_ms: int = 300
    max_challenge_ms: int = 5000  # human reaction to a prompt; replayed video responds at random times
    min_session_ms: int = 1500

    # screen-flash (services/flash.py). flash_count=0 disables; flash_enforce=0 records scores only
    flash_count: int = 3
    flash_enforce: bool = True           # set 0 on the Android emulator: its "screen" is a small window on the Mac
    flash_min_correlation: float = 0.5   # Galaxy S25+: genuine 0.95-0.99, replay on a phone screen 0.77-0.83
    flash_min_response: float = 2.0      # RMS chroma change in 8-bit units; genuine 11-19, emulator 0.3
    flash_max_background_ratio: float = 0.8  # surroundings/face response; genuine 0.47-0.52, replay 1.15-2.31
    flash_hold_ms: int = 450             # how long the app shows each colour before capturing

    store_frames: bool = False
    frames_dir: str = "data/frames"

    @property
    def challenges(self) -> list[str]:
        return [c.strip() for c in self.challenge_pool.split(",") if c.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
