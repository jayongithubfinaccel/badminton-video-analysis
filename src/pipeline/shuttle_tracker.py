"""Shuttle position tracking via TrackNetV3 (Phase D).

TrackNetV3 (qaz812345/TrackNetV3) predicts per-frame shuttlecock (x, y,
visibility) from raw video using a pretrained model — no fine-tuning needed.
This module is the pipeline's interface to those predictions: it locates (or
generates) the per-video prediction CSV, and turns the raw per-frame points
into landing-point estimates usable for zone mapping.

TrackNetV3 itself is not vendored into this repo — it's a large third-party
model with its own checkpoint weights (~140MB), set up as a sibling clone
(see docs/PRD_v2.3.md Phase D). If it isn't present on a given machine,
predictions are simply unavailable and callers fall back to the
player-position proxy (shot_detector.estimate_shuttle_position_apex).

Supersedes the earlier blob-detection-based shuttle tracker (background
subtraction + brightness/size filtering), which was never wired into the
pipeline and consistently lost the shuttle against bright court surfaces
and broadcast overlays.
"""

import csv
import sys
from pathlib import Path

from src.config import (
    SHUTTLE_CACHE_DIR,
    SHUTTLE_LANDING_PAD_FRAMES,
    TRACKNETV3_DIR,
    TRACKNETV3_INPAINTNET_CKPT,
    TRACKNETV3_TRACKNET_CKPT,
)


def ensure_ball_predictions(video_path: Path) -> Path | None:
    """Return the path to this video's shuttle-prediction CSV, generating it
    via TrackNetV3 if not already cached. Returns None if TrackNetV3 isn't
    set up on this machine.
    """
    import subprocess

    SHUTTLE_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = SHUTTLE_CACHE_DIR / f"{video_path.stem}_ball.csv"
    if cached.exists():
        return cached

    predict_script = TRACKNETV3_DIR / "predict.py"
    if not predict_script.exists() or not TRACKNETV3_TRACKNET_CKPT.exists():
        return None

    # predict.py extracts the video's stem via `video_file.split('/')[-1]` —
    # a Unix-style split that's a no-op on a Windows backslash path, which
    # then makes its os.path.join(save_dir, video_name) silently discard
    # save_dir entirely (os.path.join drops everything before an operand
    # that looks like an absolute path). Forward slashes parse correctly on
    # Windows too, so normalizing here avoids touching the vendored script.
    result = subprocess.run(
        [
            sys.executable,
            str(predict_script),
            "--video_file", str(video_path.resolve()).replace("\\", "/"),
            "--tracknet_file", str(TRACKNETV3_TRACKNET_CKPT.resolve()).replace("\\", "/"),
            "--inpaintnet_file", str(TRACKNETV3_INPAINTNET_CKPT.resolve()).replace("\\", "/"),
            "--save_dir", str(SHUTTLE_CACHE_DIR.resolve()).replace("\\", "/"),
            "--eval_mode", "nonoverlap",
        ],
        cwd=str(TRACKNETV3_DIR),
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        print(f"       WARNING: TrackNetV3 prediction failed: {result.stderr[-500:]}")
        return None

    return cached if cached.exists() else None


class ShuttleTracker:
    """Looks up real shuttle positions from a TrackNetV3 prediction CSV."""

    def __init__(self, csv_path: Path, pad_frames: int = SHUTTLE_LANDING_PAD_FRAMES):
        self._lookup: dict[int, tuple[float, float]] = {}
        with open(csv_path, newline="") as f:
            for row in csv.DictReader(f):
                if int(row["Visibility"]) == 1:
                    self._lookup[int(row["Frame"])] = (float(row["X"]), float(row["Y"]))
        self.pad_frames = pad_frames

    def at_frame(self, frame_idx: int) -> tuple[float, float] | None:
        """Raw shuttle position TrackNetV3 reported for this exact frame, or
        None if it wasn't visible. Used by the visual debug overlay (Phase
        F, docs/PRD_v2.4.md) to mark the shuttle on an arbitrary frame — as
        opposed to landing_point()'s shot-specific search over a range.
        """
        return self._lookup.get(frame_idx)

    def landing_point(self, prev_frame: int, shot_frame: int) -> tuple[float, float] | None:
        """Estimate where the shuttle was received for the shot at shot_frame.

        Searches for the shuttle's lowest on-screen point (largest pixel Y =
        closest to the court surface) between the previous shot and this one,
        skipping `pad_frames` right after the previous contact — the shuttle
        is still near the previous player's racket then, not descending
        toward its landing point. Chosen empirically; see docs/RESULTS.md
        "Phase D".
        """
        f_start = prev_frame + self.pad_frames
        f_end = shot_frame
        if f_end <= f_start:
            f_start = max(prev_frame, shot_frame - 10)

        best = None
        for f in range(f_start, f_end + 1):
            point = self._lookup.get(f)
            if point is not None and (best is None or point[1] > best[1]):
                best = point
        return best
