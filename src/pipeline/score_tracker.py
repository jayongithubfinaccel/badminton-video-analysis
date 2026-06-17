"""Score tracking — detect score from broadcast scoreboard via OCR.

Falls back to inferring score from rally wins when OCR is unreliable.
"""

import re

import cv2
import numpy as np

from src.config import SCOREBOARD_REGION


class ScoreState:
    """Current match score state."""

    def __init__(self):
        self.player1_score = 0
        self.player2_score = 0
        self.current_game = 1
        self.player1_name = "Player 1"
        self.player2_name = "Player 2"
        self.history: list[dict] = []

    def point_won(self, winner: int) -> None:
        """Record a point won by player 1 or 2."""
        if winner == 1:
            self.player1_score += 1
        else:
            self.player2_score += 1

        self.history.append({
            "point_number": len(self.history) + 1,
            "winner": winner,
            "game": self.current_game,
            "player1_score": self.player1_score,
            "player2_score": self.player2_score,
        })

    def new_game(self) -> None:
        """Start a new game/set."""
        self.current_game += 1
        self.player1_score = 0
        self.player2_score = 0


class ScoreTracker:
    """Track score from broadcast video using OCR and inference."""

    def __init__(self):
        self.state = ScoreState()
        self._ocr_reader = None
        self._ocr_available = False
        self._init_ocr()

    def _init_ocr(self) -> None:
        """Initialize EasyOCR reader."""
        try:
            import easyocr
            self._ocr_reader = easyocr.Reader(['en'], gpu=False, verbose=False)
            self._ocr_available = True
        except (ImportError, Exception):
            self._ocr_available = False

    def detect_score_from_frame(self, frame: np.ndarray) -> dict | None:
        """Try to read score from the scoreboard overlay.

        Returns dict with detected scores or None if not readable.
        """
        if not self._ocr_available:
            return None

        h, w = frame.shape[:2]

        # Extract scoreboard region
        x_start = int(w * SCOREBOARD_REGION["x_start"])
        y_start = int(h * SCOREBOARD_REGION["y_start"])
        x_end = int(w * SCOREBOARD_REGION["x_end"])
        y_end = int(h * SCOREBOARD_REGION["y_end"])

        scoreboard = frame[y_start:y_end, x_start:x_end]

        if scoreboard.size == 0:
            return None

        # OCR the scoreboard region
        try:
            results = self._ocr_reader.readtext(scoreboard)
        except Exception:
            return None

        # Parse OCR results for score patterns
        text = " ".join([r[1] for r in results])
        return self._parse_score_text(text)

    def _parse_score_text(self, text: str) -> dict | None:
        """Parse OCR text to extract scores.

        Common patterns:
        - "PLAYER1 5  PLAYER2 3"
        - "5 - 3"
        - Score digits near player names
        """
        # Look for digit patterns
        numbers = re.findall(r'\d+', text)

        if len(numbers) >= 2:
            try:
                s1 = int(numbers[0])
                s2 = int(numbers[1])
                # Sanity check: badminton scores don't exceed 30
                if 0 <= s1 <= 30 and 0 <= s2 <= 30:
                    return {"player1_score": s1, "player2_score": s2}
            except ValueError:
                pass

        return None

    def detect_player_names(self, frame: np.ndarray) -> tuple[str, str] | None:
        """Try to detect player names from scoreboard."""
        if not self._ocr_available:
            return None

        h, w = frame.shape[:2]

        # Extract scoreboard region (wider for names)
        x_start = int(w * SCOREBOARD_REGION["x_start"])
        y_start = int(h * SCOREBOARD_REGION["y_start"])
        x_end = int(w * SCOREBOARD_REGION["x_end"] * 1.2)
        y_end = int(h * SCOREBOARD_REGION["y_end"])

        scoreboard = frame[y_start:y_end, x_start:x_end]

        if scoreboard.size == 0:
            return None

        try:
            results = self._ocr_reader.readtext(scoreboard)
        except Exception:
            return None

        # Extract text that looks like player names (alphabetic, >3 chars)
        names = []
        for _, text, conf in results:
            # Filter for name-like text
            cleaned = re.sub(r'[^a-zA-Z.\s]', '', text).strip()
            if len(cleaned) >= 3 and conf > 0.3:
                names.append(cleaned)

        if len(names) >= 2:
            return names[0], names[1]
        return None

    def infer_point_winner_from_rally(
        self,
        last_shuttle_y: int,
        frame_height: int,
    ) -> int:
        """Infer who won the point based on where the shuttle ended.

        Heuristic: If the shuttle's last position is on Player 2's side (top),
        Player 1 likely won (shuttle landed there). And vice versa.
        """
        midline = frame_height / 2
        if last_shuttle_y < midline:
            return 1  # Shuttle on top = landed on Player 2's court = Player 1 wins
        return 2  # Shuttle on bottom = landed on Player 1's court = Player 2 wins
