"""Frame filtering — detect active play vs non-play frames.

Filters out replays, crowd shots, advertisements, and other non-court content.
Only passes through frames showing active court play.
"""

import cv2
import numpy as np


def is_court_visible(frame: np.ndarray, min_green_ratio: float = 0.08) -> bool:
    """Check if the court (green playing surface) is visible in the frame.

    This filters out crowd shots, close-ups, and replays that don't show the court.
    """
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Detect green court surface
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    green_ratio = np.sum(green_mask > 0) / green_mask.size
    return green_ratio >= min_green_ratio


def compute_motion_level(
    prev_frame: np.ndarray,
    curr_frame: np.ndarray,
    court_mask: np.ndarray | None = None
) -> float:
    """Compute motion level between two consecutive frames.

    Returns a value between 0 (no motion) and 1 (maximum motion).
    Optionally restricted to the court area only.
    """
    # Convert to grayscale
    prev_gray = cv2.cvtColor(prev_frame, cv2.COLOR_BGR2GRAY)
    curr_gray = cv2.cvtColor(curr_frame, cv2.COLOR_BGR2GRAY)

    # Apply Gaussian blur to reduce noise
    prev_gray = cv2.GaussianBlur(prev_gray, (5, 5), 0)
    curr_gray = cv2.GaussianBlur(curr_gray, (5, 5), 0)

    # Compute absolute difference
    diff = cv2.absdiff(prev_gray, curr_gray)

    # Apply court mask if provided
    if court_mask is not None:
        diff = cv2.bitwise_and(diff, diff, mask=court_mask)
        total_pixels = np.sum(court_mask > 0)
    else:
        total_pixels = diff.size

    if total_pixels == 0:
        return 0.0

    # Threshold to get significant motion pixels
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)
    motion_pixels = np.sum(thresh > 0)

    return motion_pixels / total_pixels


def detect_scene_change(
    prev_frame: np.ndarray,
    curr_frame: np.ndarray,
    threshold: float = 0.4
) -> bool:
    """Detect if there's a scene change (camera cut) between frames.

    Scene changes indicate transitions to replays, ads, etc.
    """
    # Use histogram comparison
    prev_hist = cv2.calcHist(
        [cv2.cvtColor(prev_frame, cv2.COLOR_BGR2HSV)],
        [0, 1], None, [50, 60], [0, 180, 0, 256]
    )
    curr_hist = cv2.calcHist(
        [cv2.cvtColor(curr_frame, cv2.COLOR_BGR2HSV)],
        [0, 1], None, [50, 60], [0, 180, 0, 256]
    )

    cv2.normalize(prev_hist, prev_hist)
    cv2.normalize(curr_hist, curr_hist)

    similarity = cv2.compareHist(prev_hist, curr_hist, cv2.HISTCMP_CORREL)
    return similarity < (1.0 - threshold)


def get_court_mask(frame: np.ndarray) -> np.ndarray:
    """Create a binary mask of the court playing area."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Detect green court surface
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    # Morphological cleanup to fill gaps
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (20, 20))
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel)

    return green_mask
