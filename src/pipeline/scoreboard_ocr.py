"""Scoreboard detection — extract rally boundaries from broadcast overlay.

Phase A approach: Uses pixel-based change detection on the scoreboard region
rather than OCR for digit reading (too unreliable at broadcast resolution).

Detection strategy:
1. Scoreboard visibility tracking (brightness in name area)
2. Frame-to-frame NCC (normalized cross-correlation) on score digit rows
3. Scoreboard visibility gaps indicate replay breaks (rally boundaries)
4. NCC drops below threshold indicate in-game score changes
"""

from dataclasses import dataclass, field

import cv2
import numpy as np

from src.config import SCOREBOARD_REGION


# Scoreboard pixel regions (calibrated for BWF broadcast at 908x480)
# These are absolute pixel coordinates
SCOREBOARD_NAME_AREA = (5, 50, 30, 145)  # y1, y2, x1, x2 (for visibility check)
P1_SCORE_ROW = (7, 27, 145, 172)  # y1, y2, x1, x2 (P1 digit + serve indicator)
P2_SCORE_ROW = (28, 50, 145, 172)  # y1, y2, x1, x2 (P2 digit + serve indicator)

# Detection thresholds
VISIBILITY_BRIGHTNESS_THRESHOLD = 60  # Mean brightness to consider scoreboard visible
NCC_CHANGE_THRESHOLD = 0.990  # NCC below this = score change detected
VISIBILITY_GAP_MIN_SECONDS = 2.0  # Gap must be ≥2s to count as rally boundary


@dataclass
class ScoreChangeEvent:
    """A detected score change (rally boundary)."""

    frame_idx: int
    timestamp: float
    change_type: str  # "pixel_change" or "visibility_gap"
    player_changed: int  # 1 or 2 (which player's score changed), 0 if unknown
    ncc_p1: float = 1.0
    ncc_p2: float = 1.0


@dataclass
class ScoreboardOCR:
    """Detect rally boundaries via pixel-based scoreboard change detection."""

    fps: float = 30.0
    sample_interval_sec: float = 1.0
    player1_name: str = "Player 1"
    player2_name: str = "Player 2"

    _score_changes: list[ScoreChangeEvent] = field(default_factory=list)
    _visibility_log: list[tuple] = field(default_factory=list)
    _names_detected: bool = False

    def __post_init__(self):
        self._score_changes = []
        self._visibility_log = []

    @property
    def is_available(self) -> bool:
        """Always available (no external deps needed for pixel detection)."""
        return True

    def get_sample_interval_frames(self) -> int:
        """Number of frames between samples."""
        return max(1, int(self.fps * self.sample_interval_sec))

    def is_scoreboard_visible(self, frame: np.ndarray) -> bool:
        """Check if the scoreboard overlay is visible."""
        y1, y2, x1, x2 = SCOREBOARD_NAME_AREA
        h, w = frame.shape[:2]
        # Adjust for different resolutions
        if w != 908:
            scale = w / 908
            y1, y2 = int(y1 * (h / 480)), int(y2 * (h / 480))
            x1, x2 = int(x1 * scale), int(x2 * scale)

        region = frame[y1:y2, x1:x2]
        gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
        return float(np.mean(gray)) > VISIBILITY_BRIGHTNESS_THRESHOLD

    def get_score_row(self, frame: np.ndarray, player: int) -> np.ndarray:
        """Extract grayscale score row for a player (1 or 2)."""
        region = P1_SCORE_ROW if player == 1 else P2_SCORE_ROW
        y1, y2, x1, x2 = region
        h, w = frame.shape[:2]
        # Adjust for different resolutions
        if w != 908:
            scale_x = w / 908
            scale_y = h / 480
            y1, y2 = int(y1 * scale_y), int(y2 * scale_y)
            x1, x2 = int(x1 * scale_x), int(x2 * scale_x)

        return cv2.cvtColor(frame[y1:y2, x1:x2], cv2.COLOR_BGR2GRAY).astype(np.float32)

    @staticmethod
    def ncc(a: np.ndarray, b: np.ndarray) -> float:
        """Normalized cross-correlation between two images."""
        a_norm = a - np.mean(a)
        b_norm = b - np.mean(b)
        denom = np.sqrt(float(np.sum(a_norm ** 2)) * float(np.sum(b_norm ** 2)))
        if denom == 0:
            return 1.0
        return float(np.sum(a_norm * b_norm)) / denom

    def detect_player_names(self, frame: np.ndarray) -> tuple[str, str] | None:
        """Try to detect player names using EasyOCR (optional enhancement).

        Falls back gracefully if OCR is not available.
        """
        try:
            import easyocr
        except ImportError:
            return None

        h, w = frame.shape[:2]
        # Name area: roughly top-left, x=30-145, y=5-50
        scoreboard = frame[5:50, 30:145]
        if scoreboard.size == 0:
            return None

        # Upscale for OCR
        scaled = cv2.resize(scoreboard, (460, 180), interpolation=cv2.INTER_CUBIC)

        try:
            import re
            reader = easyocr.Reader(["en"], gpu=False, verbose=False)
            results = reader.readtext(scaled)

            names = []
            for _, text, conf in results:
                cleaned = re.sub(r"[^a-zA-Z.\s]", "", text).strip()
                if len(cleaned) >= 3 and conf > 0.2:
                    names.append(cleaned.upper())

            if len(names) >= 2:
                self.player1_name = names[0]
                self.player2_name = names[1]
                self._names_detected = True
                return (self.player1_name, self.player2_name)
        except Exception:
            pass

        return None

    def scan_video(self, cap: cv2.VideoCapture) -> list[ScoreChangeEvent]:
        """Scan entire video for score changes.

        This is the main Phase A detection method.
        Returns list of ScoreChangeEvent marking rally boundaries.
        """
        fps = cap.get(cv2.CAP_PROP_FPS)
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_interval = self.get_sample_interval_frames()

        prev_p1: np.ndarray | None = None
        prev_p2: np.ndarray | None = None
        prev_visible = False
        hidden_start_frame: int | None = None
        last_visible_frame = 0

        self._score_changes = []
        self._visibility_log = []
        total_samples = total_frames // sample_interval

        for sample_num, frame_idx in enumerate(range(0, total_frames, sample_interval)):
            cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = cap.read()
            if not ret:
                break

            if (sample_num + 1) % 20 == 0:
                print(
                    f"       Progress: {sample_num + 1}/{total_samples} samples "
                    f"({frame_idx / fps:.0f}s / {total_frames / fps:.0f}s)"
                )

            visible = self.is_scoreboard_visible(frame)
            t = frame_idx / fps

            if visible:
                p1 = self.get_score_row(frame, 1)
                p2 = self.get_score_row(frame, 2)

                # Check for visibility gap ending (scoreboard reappeared)
                if not prev_visible and hidden_start_frame is not None:
                    gap_duration = (frame_idx - hidden_start_frame) / fps
                    if gap_duration >= VISIBILITY_GAP_MIN_SECONDS:
                        # Scoreboard was hidden for significant time = rally boundary
                        # Check if score actually changed by comparing before/after
                        # pixels — if both P1 and P2 digits changed, multiple rallies
                        # happened during the gap
                        if prev_p1 is not None:
                            ncc_p1_gap = self.ncc(prev_p1, p1)
                            ncc_p2_gap = self.ncc(prev_p2, p2)
                            # Count how many boundaries: if both changed, likely 2+
                            both_changed = (
                                ncc_p1_gap < NCC_CHANGE_THRESHOLD
                                and ncc_p2_gap < NCC_CHANGE_THRESHOLD
                            )
                        else:
                            both_changed = False
                            ncc_p1_gap = 1.0
                            ncc_p2_gap = 1.0

                        if both_changed:
                            # Multiple rallies during gap — add 2 boundaries
                            mid_frame = (hidden_start_frame + frame_idx) // 2
                            event1 = ScoreChangeEvent(
                                frame_idx=mid_frame,
                                timestamp=mid_frame / fps,
                                change_type="visibility_gap",
                                player_changed=2,  # P2 likely scored first
                            )
                            event2 = ScoreChangeEvent(
                                frame_idx=frame_idx,
                                timestamp=t,
                                change_type="visibility_gap",
                                player_changed=1,  # P1 scored second
                            )
                            self._score_changes.append(event1)
                            self._score_changes.append(event2)
                        else:
                            event = ScoreChangeEvent(
                                frame_idx=frame_idx,
                                timestamp=t,
                                change_type="visibility_gap",
                                player_changed=0,
                            )
                            self._score_changes.append(event)
                    hidden_start_frame = None

                # Check NCC with previous visible frame
                if prev_p1 is not None and prev_visible:
                    ncc_p1 = self.ncc(prev_p1, p1)
                    ncc_p2 = self.ncc(prev_p2, p2)

                    if ncc_p1 < NCC_CHANGE_THRESHOLD or ncc_p2 < NCC_CHANGE_THRESHOLD:
                        # Score changed!
                        player = 1 if ncc_p1 < ncc_p2 else 2
                        event = ScoreChangeEvent(
                            frame_idx=frame_idx,
                            timestamp=t,
                            change_type="pixel_change",
                            player_changed=player,
                            ncc_p1=ncc_p1,
                            ncc_p2=ncc_p2,
                        )
                        self._score_changes.append(event)

                prev_p1 = p1
                prev_p2 = p2
                last_visible_frame = frame_idx
            else:
                # Scoreboard not visible
                if prev_visible and hidden_start_frame is None:
                    hidden_start_frame = frame_idx

            self._visibility_log.append((frame_idx, t, visible))
            prev_visible = visible

        # Post-process: merge nearby events (within 3s) into single boundaries
        self._score_changes = self._merge_nearby_events(self._score_changes)

        return self._score_changes

    def _merge_nearby_events(
        self, events: list[ScoreChangeEvent], min_gap_sec: float = 3.0
    ) -> list[ScoreChangeEvent]:
        """Merge events that are within min_gap_sec of each other."""
        if not events:
            return []

        merged = [events[0]]
        for event in events[1:]:
            if event.timestamp - merged[-1].timestamp < min_gap_sec:
                # Keep the one with stronger signal
                if event.change_type == "visibility_gap":
                    merged[-1] = event  # Prefer visibility gap
            else:
                merged.append(event)

        return merged

    def get_score_changes(self) -> list[ScoreChangeEvent]:
        """Return all detected score changes."""
        return self._score_changes

    def get_readings(self) -> list[tuple]:
        """Return visibility log for debugging."""
        return self._visibility_log

    def get_rally_boundaries(self) -> list[dict]:
        """Convert score changes into rally boundary info."""
        boundaries = []
        for i, change in enumerate(self._score_changes):
            rally = {
                "score_sequence": i + 1,
                "end_frame": change.frame_idx,
                "end_time": change.timestamp,
                "change_type": change.change_type,
                "player_scored": change.player_changed,
            }
            boundaries.append(rally)
        return boundaries
