"""Rally segmentation — detect rally start/end boundaries.

Phase A: Uses scoreboard pixel change detection as the primary signal
for rally boundaries. A score change = one rally has ended.
"""

from dataclasses import dataclass, field

import numpy as np

from src.config import MIN_RALLY_FRAMES
from src.pipeline.scoreboard_ocr import ScoreChangeEvent


@dataclass
class Rally:
    """Represents a detected rally segment."""

    score_sequence: int  # Which point/rally (1, 2, 3, ...)
    start_frame: int
    end_frame: int | None = None
    fps: float = 30.0
    winner: int = 0  # 1 or 2 (which player scored)
    change_type: str = ""  # "pixel_change" or "visibility_gap"
    motion_levels: list[float] = field(default_factory=list)

    @property
    def start_time(self) -> float:
        return self.start_frame / self.fps

    @property
    def end_time(self) -> float | None:
        if self.end_frame is None:
            return None
        return self.end_frame / self.fps

    @property
    def duration_frames(self) -> int:
        if self.end_frame is None:
            return 0
        return self.end_frame - self.start_frame

    @property
    def duration_seconds(self) -> float:
        return self.duration_frames / self.fps

    def is_valid(self) -> bool:
        """A rally must have minimum duration to be considered valid."""
        return self.duration_frames >= MIN_RALLY_FRAMES


class RallySegmenter:
    """Segments video into rally intervals using score changes as boundaries."""

    def __init__(self, fps: float, total_frames: int):
        self.fps = fps
        self.total_frames = total_frames
        self.rallies: list[Rally] = []

    def build_rallies_from_score_changes(
        self, score_changes: list[ScoreChangeEvent]
    ) -> list[Rally]:
        """Build rally list from detected score change events.

        Each score change marks the END of a rally.
        """
        if not score_changes:
            return []

        rallies = []
        for i, change in enumerate(score_changes):
            if i == 0:
                start_frame = 0
            else:
                start_frame = score_changes[i - 1].frame_idx

            rally = Rally(
                score_sequence=i + 1,
                start_frame=start_frame,
                end_frame=change.frame_idx,
                fps=self.fps,
                winner=change.player_changed,
                change_type=change.change_type,
            )

            if rally.is_valid():
                rallies.append(rally)

        # Handle partial rally at end (video may end mid-rally)
        if score_changes:
            last_change_frame = score_changes[-1].frame_idx
            if self.total_frames - last_change_frame > MIN_RALLY_FRAMES:
                partial_rally = Rally(
                    score_sequence=len(score_changes) + 1,
                    start_frame=last_change_frame,
                    end_frame=self.total_frames,
                    fps=self.fps,
                    winner=0,  # Unknown — video ended
                    change_type="partial",
                )
                rallies.append(partial_rally)

        self.rallies = rallies
        return rallies

    def get_rallies(self) -> list[Rally]:
        return self.rallies
