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

# Player names (fallback if OCR cannot detect)
# Player 1 = far court (top of frame) = first listed in BWF broadcast
# Player 2 = near court (bottom of frame) = second listed
PLAYER1_NAME_FALLBACK = "DONG T.Y."
PLAYER2_NAME_FALLBACK = "FARHAN"
