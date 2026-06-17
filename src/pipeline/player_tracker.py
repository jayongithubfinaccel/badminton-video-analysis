"""Player tracking — identify which player hit the shuttle.

For broadcast footage, we use position-based heuristics:
- Bottom of frame = Player 1 (near player)
- Top of frame = Player 2 (far player)
"""

import cv2
import numpy as np


class PlayerPosition:
    """Detected player position."""

    def __init__(self, x: int, y: int, player_id: int):
        self.x = x
        self.y = y
        self.player_id = player_id  # 1 or 2


class PlayerTracker:
    """Track player positions to attribute shots."""

    def __init__(self, frame_height: int):
        self.frame_height = frame_height
        self.midline = frame_height // 2  # Approximate net position

    def detect_players(self, frame: np.ndarray) -> list[PlayerPosition]:
        """Detect player positions using color/motion."""
        # For broadcast footage, players are typically distinguishable
        # by their position relative to the net (frame midline)
        # This is a simplified detection using contour analysis

        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        h, w = frame.shape[:2]

        # Create mask for non-court areas that might be players
        # Players are typically non-green objects on the green court
        lower_green = np.array([35, 40, 40])
        upper_green = np.array([85, 255, 255])
        court_mask = cv2.inRange(hsv, lower_green, upper_green)

        # Invert to get non-court objects
        non_court = cv2.bitwise_not(court_mask)

        # Focus on court region (middle 60% of frame height, middle 80% of width)
        roi_mask = np.zeros_like(non_court)
        y_start = int(h * 0.2)
        y_end = int(h * 0.85)
        x_start = int(w * 0.1)
        x_end = int(w * 0.9)
        roi_mask[y_start:y_end, x_start:x_end] = 255

        player_mask = cv2.bitwise_and(non_court, roi_mask)

        # Morphological cleanup
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (10, 10))
        player_mask = cv2.morphologyEx(player_mask, cv2.MORPH_CLOSE, kernel)
        player_mask = cv2.morphologyEx(player_mask, cv2.MORPH_OPEN, kernel)

        # Find contours
        contours, _ = cv2.findContours(player_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        # Filter by size (players should be medium-sized blobs)
        min_player_area = (h * w) * 0.002
        max_player_area = (h * w) * 0.05
        players = []

        for contour in contours:
            area = cv2.contourArea(contour)
            if min_player_area <= area <= max_player_area:
                M = cv2.moments(contour)
                if M["m00"] > 0:
                    cx = int(M["m10"] / M["m00"])
                    cy = int(M["m01"] / M["m00"])
                    players.append((cx, cy, area))

        # Sort by y-coordinate (top to bottom)
        players.sort(key=lambda p: p[1])

        result = []
        if len(players) >= 2:
            # Top player = Player 2 (far side), Bottom player = Player 1 (near side)
            result.append(PlayerPosition(players[0][0], players[0][1], 2))
            result.append(PlayerPosition(players[-1][0], players[-1][1], 1))
        elif len(players) == 1:
            # Determine which player based on position
            px, py, _ = players[0]
            if py > self.midline:
                result.append(PlayerPosition(px, py, 1))
            else:
                result.append(PlayerPosition(px, py, 2))

        return result

    def attribute_shot(
        self,
        shuttle_x: int,
        shuttle_y: int,
        players: list[PlayerPosition]
    ) -> int:
        """Determine which player hit the shuttle based on proximity.

        Returns player_id (1 or 2).
        """
        if not players:
            # Default: use frame position
            if shuttle_y > self.midline:
                return 1  # Bottom half = Player 1
            return 2  # Top half = Player 2

        # Find closest player
        min_dist = float('inf')
        closest_player = 1

        for player in players:
            dist = np.sqrt((shuttle_x - player.x) ** 2 + (shuttle_y - player.y) ** 2)
            if dist < min_dist:
                min_dist = dist
                closest_player = player.player_id

        return closest_player
