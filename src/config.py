"""Configuration constants for the badminton video analysis service."""

from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).parent.parent
INPUT_FOLDER = PROJECT_ROOT / "input"
OUTPUT_FOLDER = PROJECT_ROOT / "output"

# Input constraints
MAX_FILE_SIZE_MB = 100
MAX_DURATION_MINUTES = 20
SUPPORTED_FORMATS = [".mp4"]

# Processing
MIN_RESOLUTION = 720
CONFIDENCE_THRESHOLD = 0.5

# Court zone grid (9 zones per half)
# Zone layout from player's perspective facing net:
#   Baseline (back)
#   [1] [2] [3]   <- back row
#   [4] [5] [6]   <- mid row
#   [7] [8] [9]   <- front row (near net)
#   NET
NUM_ZONES = 9

# Video processing
FRAME_SKIP = 2  # Process every Nth frame for speed
RALLY_MOTION_THRESHOLD = 0.02  # Motion level to detect active play
RALLY_PAUSE_FRAMES = 45  # Frames of low motion to declare rally end (~1.5s at 30fps)
MIN_RALLY_FRAMES = 30  # Minimum frames for a valid rally (~1s)

# Shuttle detection
SHUTTLE_MIN_AREA = 10
SHUTTLE_MAX_AREA = 300
SHUTTLE_BRIGHTNESS_THRESHOLD = 200

# Scoreboard OCR (Phase A)
# Region coordinates relative to frame dimensions for BWF broadcast overlays
SCOREBOARD_REGION = {
    "x_start": 0.0,
    "y_start": 0.0,
    "x_end": 0.18,
    "y_end": 0.12,
}
SCOREBOARD_SAMPLE_INTERVAL = 1.0  # Sample scoreboard every 1.0 seconds (Phase A)
SCOREBOARD_CONFIRMATION_FRAMES = 3  # Require N consistent readings to confirm score change

# Player names (fallback if OCR cannot detect).
# Must stay generic — never a specific tournament's real player names.
# A real name belongs to one video; silently reusing it for a different
# video produced wrong output and is what this fallback exists to prevent
# (see docs/PRD_v2.3.md Section 7.4 and 14.3).
# Player 1 = far court (top of frame), Player 2 = near court (bottom of frame).
PLAYER1_NAME_FALLBACK = "Player 1"
PLAYER2_NAME_FALLBACK = "Player 2"

# Shuttle tracking (Phase D) — TrackNetV3 is an external model with its own
# large checkpoint weights; it lives as a sibling clone, not inside this repo.
# If it isn't present on a given machine, ensure_ball_predictions() returns
# None and callers fall back to the player-position proxy (Phase C.1).
TRACKNETV3_DIR = PROJECT_ROOT.parent / "TrackNetV3_src"
TRACKNETV3_TRACKNET_CKPT = TRACKNETV3_DIR / "ckpts" / "TrackNet_best.pt"
TRACKNETV3_INPAINTNET_CKPT = TRACKNETV3_DIR / "ckpts" / "InpaintNet_best.pt"
SHUTTLE_CACHE_DIR = PROJECT_ROOT / "data" / "shuttle_cache"

# Frames to skip immediately after the previous shot before searching for
# this shot's landing point. The shuttle is still near the previous player's
# racket right after contact, which is noise, not the landing point we want.
# Chosen via sweep against ground truth (docs/RESULTS.md "Phase D").
SHUTTLE_LANDING_PAD_FRAMES = 5

# Visual debug tooling (Phase F, docs/PRD_v2.4.md) — diagnostic only, never
# consumed by scoring logic. Both --debug-frames/--debug-video are off by
# default; these constants only take effect when a user explicitly requests
# one of those flags.
DEBUG_FRAMES_FOLDER = OUTPUT_FOLDER / "debug_frames"
DEBUG_VIDEO_FOLDER = OUTPUT_FOLDER / "debug_video"
DEFAULT_DEBUG_FRAME_SAMPLE_COUNT = 30
