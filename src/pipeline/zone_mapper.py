"""Zone mapper — maps shuttle landing coordinates to 9-zone court grid."""

import numpy as np

from src.pipeline.court_detector import (
    COURT_LENGTH,
    COURT_WIDTH,
    court_coords_to_zone,
    pixel_to_court_coords,
)


class ZoneMapper:
    """Maps pixel coordinates to court zones using homography."""

    def __init__(self, homography: np.ndarray | None, frame_height: int, frame_width: int):
        self.homography = homography
        self.frame_height = frame_height
        self.frame_width = frame_width

    def pixel_to_zone(self, x: int, y: int) -> tuple[int, int]:
        """Map pixel coordinates to zone for each player's half.

        Returns (zone_on_top_half, zone_on_bottom_half).
        Zone is 0 if the point is not on that player's half.
        """
        if self.homography is not None:
            # Use homography for accurate mapping
            court_pos = pixel_to_court_coords((x, y), self.homography)
            if court_pos is not None:
                cx, cy = court_pos
                zone_top = court_coords_to_zone(cx, cy, "top")
                zone_bottom = court_coords_to_zone(cx, cy, "bottom")
                return zone_top, zone_bottom

        # Fallback: use simple proportional mapping based on frame position
        return self._fallback_zone_mapping(x, y)

    def _fallback_zone_mapping(self, x: int, y: int) -> tuple[int, int]:
        """Simple zone mapping based on frame position when homography is unavailable.

        For broadcast footage with camera behind one baseline:
        - Top of frame = far court (Player 2's half)
        - Bottom of frame = near court (Player 1's half)
        - Court typically occupies middle portion of frame
        """
        # Estimate court boundaries in frame
        # Court is roughly in the center 70% vertically, 50% horizontally
        court_top = self.frame_height * 0.20
        court_bottom = self.frame_height * 0.85
        court_left = self.frame_width * 0.20
        court_right = self.frame_width * 0.80
        court_mid_y = (court_top + court_bottom) / 2

        # Check if point is within court area
        if x < court_left or x > court_right:
            return 0, 0
        if y < court_top or y > court_bottom:
            return 0, 0

        # Normalize within court
        rel_x = (x - court_left) / (court_right - court_left)
        rel_y = (y - court_top) / (court_bottom - court_top)

        # Column (left to right from camera view)
        if rel_x < 1 / 3:
            col = 0
        elif rel_x < 2 / 3:
            col = 1
        else:
            col = 2

        # Determine which half and row
        zone_top = 0
        zone_bottom = 0

        if rel_y < 0.5:
            # Top half = Player 2's court
            half_rel_y = rel_y / 0.5  # 0 to 1 within top half
            # For top player: 0=baseline(back), 1=net(front)
            if half_rel_y < 1 / 3:
                row = 0  # Back (Z1-3)
            elif half_rel_y < 2 / 3:
                row = 1  # Mid (Z4-6)
            else:
                row = 2  # Front (Z7-9)
            zone_top = row * 3 + col + 1
        else:
            # Bottom half = Player 1's court
            half_rel_y = (rel_y - 0.5) / 0.5  # 0 to 1 within bottom half
            # For bottom player: 0=net(front), 1=baseline(back)
            if half_rel_y < 1 / 3:
                row = 2  # Front/net (Z7-9)
            elif half_rel_y < 2 / 3:
                row = 1  # Mid (Z4-6)
            else:
                row = 0  # Back/baseline (Z1-3)
            zone_bottom = row * 3 + col + 1

        return zone_top, zone_bottom

    def get_landing_zone(self, x: int, y: int) -> dict:
        """Get zone information for a landing position.

        Returns dict with player attribution and zone.
        """
        zone_top, zone_bottom = self.pixel_to_zone(x, y)

        if zone_top > 0:
            return {"player_half": 2, "zone": zone_top}
        elif zone_bottom > 0:
            return {"player_half": 1, "zone": zone_bottom}
        else:
            # Outside court — estimate based on y position
            if y < self.frame_height / 2:
                return {"player_half": 2, "zone": 5}  # Default center
            return {"player_half": 1, "zone": 5}
