"""Court detection and homography transformation.

Detects badminton court boundaries in broadcast footage and computes
a perspective transform to map pixel coordinates to court positions.
"""

import cv2
import numpy as np


# Standard badminton court dimensions (in cm)
COURT_WIDTH = 610  # singles width
COURT_LENGTH = 1340  # full court length
HALF_COURT_LENGTH = 670  # one player's half


def detect_court_lines(frame: np.ndarray) -> list[np.ndarray]:
    """Detect court lines using color filtering and Hough transform."""
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Court lines are typically white/yellow on green/blue surface
    # White lines
    lower_white = np.array([0, 0, 180])
    upper_white = np.array([180, 60, 255])
    white_mask = cv2.inRange(hsv, lower_white, upper_white)

    # Yellow lines (some courts)
    lower_yellow = np.array([15, 80, 180])
    upper_yellow = np.array([35, 255, 255])
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    line_mask = cv2.bitwise_or(white_mask, yellow_mask)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_CLOSE, kernel)
    line_mask = cv2.morphologyEx(line_mask, cv2.MORPH_OPEN, kernel)

    # Detect lines
    lines = cv2.HoughLinesP(
        line_mask, 1, np.pi / 180, threshold=80,
        minLineLength=50, maxLineGap=20
    )

    return lines if lines is not None else []


def detect_court_corners(frame: np.ndarray) -> np.ndarray | None:
    """Detect the four corners of the court playing area.

    Returns 4 corners in order: top-left, top-right, bottom-right, bottom-left
    (from camera's perspective).
    """
    h, w = frame.shape[:2]
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Detect green court surface
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)

    # Morphological cleanup
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 15))
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel)
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel)

    # Find largest green contour (the court)
    contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    if not contours:
        return None

    # Get the largest contour
    largest = max(contours, key=cv2.contourArea)
    area = cv2.contourArea(largest)

    # Court should be at least 10% of frame area
    if area < (h * w * 0.1):
        return None

    # Approximate to polygon
    epsilon = 0.02 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)

    # Try to get 4 corners
    if len(approx) >= 4:
        # Use convex hull and find extreme points
        hull = cv2.convexHull(largest)
        rect = cv2.minAreaRect(hull)
        box = cv2.boxPoints(rect)
        box = np.int32(box)

        # Order points: top-left, top-right, bottom-right, bottom-left
        return order_points(box.astype(np.float32))

    return None


def order_points(pts: np.ndarray) -> np.ndarray:
    """Order 4 points as: top-left, top-right, bottom-right, bottom-left."""
    rect = np.zeros((4, 2), dtype=np.float32)

    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]  # top-left has smallest sum
    rect[2] = pts[np.argmax(s)]  # bottom-right has largest sum

    d = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(d)]  # top-right has smallest difference
    rect[3] = pts[np.argmax(d)]  # bottom-left has largest difference

    return rect


def compute_homography(court_corners: np.ndarray) -> np.ndarray | None:
    """Compute homography from image court corners to top-down court coordinates.

    Maps the detected court quadrilateral to a standard top-down rectangle.
    """
    if court_corners is None or len(court_corners) != 4:
        return None

    # Destination points: top-down view of full court
    # Using normalized coordinates (0-1 range for the court)
    dst_points = np.array([
        [0, 0],           # top-left
        [COURT_WIDTH, 0],  # top-right
        [COURT_WIDTH, COURT_LENGTH],  # bottom-right
        [0, COURT_LENGTH],  # bottom-left
    ], dtype=np.float32)

    H, status = cv2.findHomography(court_corners, dst_points)
    return H


def pixel_to_court_coords(
    pixel_point: tuple[int, int],
    homography: np.ndarray
) -> tuple[float, float] | None:
    """Transform pixel coordinates to court coordinates using homography."""
    if homography is None:
        return None

    pt = np.array([[[pixel_point[0], pixel_point[1]]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(pt, homography)

    x, y = transformed[0][0]
    return float(x), float(y)


def court_coords_to_zone(
    x: float, y: float, player_half: str = "bottom"
) -> int:
    """Map court coordinates to zone 1-9.

    Zone grid (from player's perspective facing net):
        Baseline (back)
        [1] [2] [3]   <- back row
        [4] [5] [6]   <- mid row
        [7] [8] [9]   <- front row (near net)
        NET

    Args:
        x: Court x coordinate (0 to COURT_WIDTH)
        y: Court y coordinate (0 to COURT_LENGTH)
        player_half: "top" or "bottom" — which player's half to map to

    Returns:
        Zone number 1-9, or 0 if outside court.
    """
    # Determine which half the point is in
    if player_half == "bottom":
        # Bottom player's half: y from COURT_LENGTH/2 to COURT_LENGTH
        half_y_start = COURT_LENGTH / 2
        half_y_end = COURT_LENGTH
    else:
        # Top player's half: y from 0 to COURT_LENGTH/2
        half_y_start = 0
        half_y_end = COURT_LENGTH / 2

    # Check if point is in this half
    if y < half_y_start or y > half_y_end:
        return 0  # Not in this player's half

    # Normalize position within the half (0 to 1)
    rel_y = (y - half_y_start) / (half_y_end - half_y_start)
    rel_x = x / COURT_WIDTH

    # Clamp
    rel_x = max(0.0, min(1.0, rel_x))
    rel_y = max(0.0, min(1.0, rel_y))

    # Determine column (left=0, center=1, right=2)
    if rel_x < 1 / 3:
        col = 0
    elif rel_x < 2 / 3:
        col = 1
    else:
        col = 2

    # Determine row based on player perspective
    if player_half == "bottom":
        # For bottom player: back is at middle of court (top of their half)
        # rel_y=0 is near net (middle of court), rel_y=1 is baseline (bottom)
        if rel_y < 1 / 3:
            row = 2  # Front (near net) -> zones 7,8,9
        elif rel_y < 2 / 3:
            row = 1  # Mid -> zones 4,5,6
        else:
            row = 0  # Back (baseline) -> zones 1,2,3
    else:
        # For top player: back is at top of frame (baseline)
        # rel_y=0 is baseline (top), rel_y=1 is near net (middle of court)
        if rel_y < 1 / 3:
            row = 0  # Back (baseline) -> zones 1,2,3
        elif rel_y < 2 / 3:
            row = 1  # Mid -> zones 4,5,6
        else:
            row = 2  # Front (near net) -> zones 7,8,9

    # Zone = row*3 + col + 1
    zone = row * 3 + col + 1
    return zone
