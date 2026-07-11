"""Court detection and homography transformation.

Detects badminton court boundaries in broadcast footage and computes
a perspective transform to map pixel coordinates to court positions.
"""

import math

import cv2
import numpy as np

from src.pipeline.zone_grid import zone_number_real

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

    # Use the convex hull's own extreme points, NOT a minAreaRect fit.
    # minAreaRect always returns an axis-aligned rectangle, which destroys
    # the actual trapezoid shape a perspective camera sees (the far baseline
    # is narrower than the near baseline). Taking the 4 extreme points of the
    # hull directly (by x+y and x-y) preserves that trapezoid, which is
    # exactly what compute_homography() below needs to be meaningful.
    hull = cv2.convexHull(largest).reshape(-1, 2).astype(np.float32)
    if len(hull) < 4:
        return None

    return order_points(hull)


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


def _line_coeffs(p1: tuple[float, float], p2: tuple[float, float]) -> tuple[float, float, float]:
    """(a, b, c) for the line through p1, p2 in the form a*x + b*y = c."""
    x1, y1 = p1
    x2, y2 = p2
    a = y2 - y1
    b = x1 - x2
    c = a * x1 + b * y1
    return a, b, c


def _line_intersection(
    line1: tuple[tuple[float, float], tuple[float, float]],
    line2: tuple[tuple[float, float], tuple[float, float]],
) -> tuple[float, float] | None:
    """Intersection of two lines, each given as a (p1, p2) point pair.
    Returns None if the lines are (near-)parallel.
    """
    a1, b1, c1 = _line_coeffs(*line1)
    a2, b2, c2 = _line_coeffs(*line2)
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-6:
        return None
    x = (c1 * b2 - c2 * b1) / det
    y = (a1 * c2 - a2 * c1) / det
    return x, y


def _point_to_line_distance(
    pt: tuple[float, float], p1: tuple[float, float], p2: tuple[float, float]
) -> float:
    a, b, c = _line_coeffs(p1, p2)
    norm = math.hypot(a, b)
    if norm < 1e-6:
        return math.hypot(pt[0] - p1[0], pt[1] - p1[1])
    return abs(a * pt[0] + b * pt[1] - c) / norm


def refine_corners_with_lines(
    frame: np.ndarray, corners: np.ndarray, max_shift_frac: float = 0.12
) -> np.ndarray:
    """Snap the coarse green-surface corners to the actual detected white
    boundary lines, when confident lines are found for enough edges.

    `detect_court_corners()` finds the green PLAYING SURFACE's own extreme
    points, which isn't always exactly the true white boundary line: the
    green mat can run a little short of it (undershoot — confirmed visually
    on this project's own generated debug frames, see docs/PRD_v2.6.md) or
    a little past it (overshoot, e.g. shadow/lighting bleeding the green
    color threshold outward, or non-court frames like a replay/celebration
    shot being misdetected entirely). Either way, the painted white line
    itself is the ground truth boundary — not the colored surface next to
    it — so this fits a line to the Hough segments (from
    `detect_court_lines`) that match each of the coarse quadrilateral's 4
    edges by angle and proximity, and re-intersects adjacent fitted lines
    for a boundary-accurate corner.

    Falls back to the coarse corner, per-edge or entirely, whenever fewer
    than 2 of the 4 edges get a confident line match, or a refined corner
    would move implausibly far (`max_shift_frac` of that quadrilateral's
    own average edge length) from the coarse estimate — a bad line match
    (e.g. snapping to a service line or an ad-board edge instead of the
    true boundary) should degrade to the pre-refinement behavior, not
    silently produce a worse box than doing nothing.
    """
    tl, tr, br, bl = (np.asarray(p, dtype=np.float64) for p in corners)
    coarse_edges = {
        "top": (tl, tr),
        "right": (tr, br),
        "bottom": (br, bl),
        "left": (bl, tl),
    }

    lines = detect_court_lines(frame)
    if lines is None or len(lines) == 0:
        return corners

    refined_edges: dict[str, tuple[tuple[float, float], tuple[float, float]]] = {}
    for name, (p1, p2) in coarse_edges.items():
        edge_vec = p2 - p1
        edge_len = float(np.linalg.norm(edge_vec))
        if edge_len < 1e-6:
            continue
        edge_angle = math.degrees(math.atan2(edge_vec[1], edge_vec[0]))

        inlier_points = []
        for seg in lines:
            x1, y1, x2, y2 = seg[0]
            seg_angle = math.degrees(math.atan2(y2 - y1, x2 - x1))
            # Angle difference mod 180 (a line has no direction/polarity).
            angle_diff = abs(((seg_angle - edge_angle + 90) % 180) - 90)
            if angle_diff > 12:
                continue
            mid = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            if _point_to_line_distance(mid, tuple(p1), tuple(p2)) > 0.15 * edge_len:
                continue
            inlier_points.append((x1, y1))
            inlier_points.append((x2, y2))

        if len(inlier_points) < 4:  # need at least ~2 segments' worth
            continue

        pts = np.array(inlier_points, dtype=np.float32)
        vx, vy, x0, y0 = cv2.fitLine(pts, cv2.DIST_L2, 0, 0.01, 0.01).flatten()
        fitted_p1 = (float(x0), float(y0))
        fitted_p2 = (float(x0 + vx * edge_len), float(y0 + vy * edge_len))
        refined_edges[name] = (fitted_p1, fitted_p2)

    if len(refined_edges) < 2:
        return corners

    def edge_or_fallback(name, fallback_p1, fallback_p2):
        return refined_edges.get(name, (tuple(fallback_p1), tuple(fallback_p2)))

    top = edge_or_fallback("top", tl, tr)
    right = edge_or_fallback("right", tr, br)
    bottom = edge_or_fallback("bottom", br, bl)
    left = edge_or_fallback("left", bl, tl)

    corner_lines = {
        "tl": (top, left), "tr": (top, right),
        "br": (bottom, right), "bl": (bottom, left),
    }
    fallback_corners = {"tl": tl, "tr": tr, "br": br, "bl": bl}

    avg_edge_len = float(np.mean([
        np.linalg.norm(tr - tl), np.linalg.norm(br - tr),
        np.linalg.norm(bl - br), np.linalg.norm(tl - bl),
    ]))

    result = []
    for key in ("tl", "tr", "br", "bl"):
        line_a, line_b = corner_lines[key]
        fallback = fallback_corners[key]
        intersection = _line_intersection(line_a, line_b)
        if intersection is None:
            result.append(fallback)
            continue
        shift = math.hypot(intersection[0] - fallback[0], intersection[1] - fallback[1])
        result.append(fallback if shift > max_shift_frac * avg_edge_len else intersection)

    return np.array(result, dtype=np.float32)


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

    # net_axis_frac: 0 at this half's own baseline, 1 at the net (see
    # zone_grid.zone_number_real). rel_x: raw on-screen-left(0)->right(1)
    # fraction; zone_number_real applies the top/bottom mirror internally.
    if player_half == "bottom":
        # rel=0 at half_y_start (net), rel=1 at half_y_end (own baseline) —
        # invert so 0 always means "this half's own baseline".
        rel_y = (y - half_y_start) / (half_y_end - half_y_start)
        net_axis_frac = 1.0 - rel_y
    else:
        # rel=0 at half_y_start (own baseline/top of frame), rel=1 at
        # half_y_end (net) — already in the "0=baseline,1=net" orientation.
        net_axis_frac = (y - half_y_start) / (half_y_end - half_y_start)

    rel_x = x / COURT_WIDTH

    # These ARE true court-plane fractions (not a player-position-derived
    # proxy box), so the row axis uses the real BWF service-line banding
    # (zone_number_real) rather than equal thirds — see zone_grid.py.
    return zone_number_real(net_axis_frac, rel_x, player_half)


def zone_from_court_coords(x: float, y: float) -> tuple[str, int]:
    """Map real-world court coordinates to (half, zone), determining the half
    automatically from y instead of requiring the caller to already know it.
    """
    half = "top" if y < COURT_LENGTH / 2 else "bottom"
    return half, court_coords_to_zone(x, y, half)


def calibrate_homography(
    cap: cv2.VideoCapture,
    fps: float,
    total_frames: int,
    sample_stride_sec: float = 1.0,
    rally_ranges: list[tuple[int, int]] | None = None,
    min_valid_samples: int = 8,
) -> tuple[np.ndarray | None, int]:
    """Sample frames, detect the court quadrilateral in each (refined against
    the actual detected white lines — see `refine_corners_with_lines`), and
    compute one stable per-video homography from the median of valid
    detections.

    Returns (homography_or_None, num_valid_samples). Callers should treat a
    None homography (or a low sample count) as "detection unreliable for this
    video" and fall back to the player-position-derived calibration instead
    — this is a validated enhancement, not a forced replacement.
    """
    stride = max(1, int(fps * sample_stride_sec))
    ranges = rally_ranges if rally_ranges else [(0, total_frames)]

    valid_corners: list[np.ndarray] = []
    for start, end in ranges:
        for frame_idx in range(start, min(end, total_frames), stride):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                continue
            corners = detect_court_corners(frame)
            if corners is None:
                continue
            corners = refine_corners_with_lines(frame, corners)

            tl, tr, br, bl = corners
            top_w = float(np.linalg.norm(tr - tl))
            bot_w = float(np.linalg.norm(br - bl))
            # Sanity check, not a per-video tuned value: this camera setup is
            # elevated behind one baseline, so the near (bottom) edge must be
            # at least as wide as the far (top) edge. A detection that
            # violates this is almost certainly a misdetection (e.g. ad
            # boards, a replay frame), not a different valid camera angle.
            if bot_w < top_w:
                continue

            valid_corners.append(corners)

    if len(valid_corners) < min_valid_samples:
        return None, len(valid_corners)

    stacked = np.stack(valid_corners, axis=0)  # (N, 4, 2)
    median_corners = np.median(stacked, axis=0).astype(np.float32)

    homography = compute_homography(median_corners)
    return homography, len(valid_corners)
