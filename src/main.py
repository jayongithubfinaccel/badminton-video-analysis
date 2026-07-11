"""Main analysis pipeline — orchestrates all stages from video to CSV output.

Phase B: Per-shot tracking within rallies.
- Phase A: Scoreboard-driven rally segmentation (score changes = rally boundaries)
- Phase B: Shot detection via motion direction analysis within each rally
- Alternation rule: shots alternate between players
- Zone mapping: each shot landing mapped to 9-zone grid
- Output: per-shot CSV matching ground truth format
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

import cv2

from src.config import (
    DEBUG_FRAMES_FOLDER,
    DEBUG_VIDEO_FOLDER,
    DEFAULT_DEBUG_FRAME_SAMPLE_COUNT,
    INPUT_FOLDER,
    OUTPUT_FOLDER,
    PLAYER1_NAME_FALLBACK,
    PLAYER2_NAME_FALLBACK,
    SCOREBOARD_SAMPLE_INTERVAL,
)
from src.pipeline.court_calibration import (
    CourtCalibration,
    calibrate_from_video,
    recalibrate_from_shuttle_positions,
)
from src.pipeline.debug_overlay import draw_overlays
from src.pipeline.export import generate_per_shot_output, generate_rally_output
from src.pipeline.frame_sampler import sample_frame_indices
from src.pipeline.player_detector import detect_players, detect_rackets
from src.pipeline.rally_segmenter import Rally, RallySegmenter
from src.pipeline.scoreboard_ocr import ScoreboardOCR
from src.pipeline.shot_detector import Shot, ShotDetector
from src.pipeline.shuttle_tracker import ShuttleTracker, ensure_ball_predictions
from src.pipeline.validator import ValidationError, validate_video

# Lunge-apex search window (each side, in frames @ ~30fps => ~0.4s). Chosen by
# sweeping 0-16 frames against ground truth (docs/RESULTS.md "Phase C.1") —
# this value gave the best combination of exact-zone accuracy and
# distributional fit without being a single-sample-noise outlier.
LUNGE_APEX_WINDOW_FRAMES = 12


class AnalysisPipeline:
    """Orchestrates the video analysis pipeline.

    Phase A: Rally detection via scoreboard pixel detection.
    Phase B: Shot-level tracking within each rally.
    """

    def __init__(
        self,
        video_path: str | Path,
        debug_frames: int | None = None,
        debug_video: bool = False,
        use_homography: bool = False,
    ):
        self.video_path = Path(video_path)
        self.use_homography = use_homography
        self.cap: cv2.VideoCapture | None = None
        self.fps: float = 30.0
        self.frame_count: int = 0
        self.frame_width: int = 0
        self.frame_height: int = 0
        self.player1_name = PLAYER1_NAME_FALLBACK
        self.player2_name = PLAYER2_NAME_FALLBACK

        # Visual debug tooling (Phase F, docs/PRD_v2.4.md) — off unless
        # explicitly requested. `calibration`/`shuttle_tracker`/
        # `_resolved_ranges` are populated by _detect_shots() and reused
        # here so the debug renderer doesn't redo calibration/TrackNetV3 setup.
        self.debug_frames = debug_frames
        self.debug_video = debug_video
        self.calibration: CourtCalibration | None = None
        self.shuttle_tracker: ShuttleTracker | None = None
        self._resolved_ranges: list[tuple[int, int]] = []

    def run(self) -> Path:
        """Run the full analysis pipeline. Returns path to output file."""
        print(f"[1/6] Validating input: {self.video_path.name}")
        validated_path = validate_video(self.video_path)

        print("[2/6] Opening video...")
        self._open_video(validated_path)

        print("[3/6] Scanning scoreboard for player names and score changes...")
        scoreboard_ocr = self._scan_scoreboard()

        print("[4/6] Building rally segments from score changes...")
        rallies = self._build_rallies(scoreboard_ocr)

        print("[5/6] Detecting shots within each rally...")
        all_shots = self._detect_shots(rallies)

        print("[6/6] Generating per-shot CSV output...")
        output_path = self._generate_output(rallies, all_shots)

        if self.debug_frames or self.debug_video:
            print("[debug] Rendering visual QA overlays (Phase F)...")
            self._render_debug_outputs()

        if self.cap:
            self.cap.release()

        return output_path

    def _open_video(self, path: Path) -> None:
        """Open video and extract metadata."""
        self.cap = cv2.VideoCapture(str(path))
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video: {path}")

        self.fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.frame_count = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.frame_width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.frame_height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

        print(
            f"       Video: {self.frame_width}x{self.frame_height} @ {self.fps:.1f}fps, "
            f"{self.frame_count} frames ({self.frame_count/self.fps:.1f}s)"
        )

    def _scan_scoreboard(self) -> ScoreboardOCR:
        """Scan the entire video for scoreboard changes.

        Uses pixel-based detection: NCC on score digit rows + visibility gaps.
        """
        if self.cap is None:
            raise RuntimeError("Video not opened")

        ocr = ScoreboardOCR(
            fps=self.fps,
            sample_interval_sec=SCOREBOARD_SAMPLE_INTERVAL,
        )

        # --- Pass 1: Detect player names from early frames ---
        print("       Detecting player names...")
        names_found = False
        for frame_idx in range(0, min(int(self.fps * 5), self.frame_count), int(self.fps)):
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
            ret, frame = self.cap.read()
            if not ret:
                continue

            if ocr.is_scoreboard_visible(frame):
                names = ocr.detect_player_names(frame)
                if names:
                    self.player1_name = names[0]
                    self.player2_name = names[1]
                    names_found = True
                    print(f"       Players: {self.player1_name} vs {self.player2_name}")
                    break

        if not names_found:
            print(
                f"       WARNING: could not detect player names from scoreboard — "
                f"using generic fallback: {self.player1_name} vs {self.player2_name}"
            )

        # --- Pass 2: Scan for score changes via pixel detection ---
        print("       Scanning for score changes (pixel-based)...")
        score_changes = ocr.scan_video(self.cap)

        print(f"       Total score changes detected: {len(score_changes)}")
        for i, change in enumerate(score_changes):
            player_str = f"Player {change.player_changed}" if change.player_changed else "unknown"
            print(
                f"       #{i + 1} at {change.timestamp:.1f}s "
                f"[{change.change_type}] scored by: {player_str}"
            )

        return ocr

    def _build_rallies(self, ocr: ScoreboardOCR) -> list[Rally]:
        """Build rally segments from score changes."""
        segmenter = RallySegmenter(self.fps, self.frame_count)
        score_changes = ocr.get_score_changes()

        rallies = segmenter.build_rallies_from_score_changes(score_changes)

        print(f"       Detected {len(rallies)} rallies:")
        for rally in rallies:
            winner_str = f"Player {rally.winner}" if rally.winner > 0 else "partial"
            print(
                f"         Score {rally.score_sequence}: "
                f"frames {rally.start_frame}-{rally.end_frame} "
                f"({rally.duration_seconds:.1f}s) -> {winner_str}"
            )

        return rallies

    def _generate_output(self, rallies: list[Rally], all_shots: list[Shot]) -> Path:
        """Generate the per-shot CSV output file."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{self.video_path.stem}_analysis_{timestamp}"
        output_path = OUTPUT_FOLDER / filename

        # Apply last-shot logic and build output data
        shot_data = self._build_shot_output(rallies, all_shots)

        csv_path = generate_per_shot_output(
            shot_data,
            output_path,
            player1_name=self.player1_name,
            player2_name=self.player2_name,
        )

        return csv_path

    def _detect_shots(self, rallies: list[Rally]) -> list[Shot]:
        """Detect individual shots within each rally."""
        if self.cap is None:
            return []

        # Resolve each rally's analyzed start frame once (used both for
        # calibration sampling and shot detection) — skip intro footage for
        # the rally starting at frame 0.
        intro_skip_frames = int(self.fps * 6)
        resolved_ranges: list[tuple[int, int]] = []
        for rally in rallies:
            if rally.end_frame is None:
                continue
            start_frame = intro_skip_frames if rally.start_frame == 0 else rally.start_frame
            resolved_ranges.append((start_frame, rally.end_frame))

        self._resolved_ranges = resolved_ranges

        print("       Calibrating court bounds from observed player positions...")
        calibration = calibrate_from_video(
            self.cap,
            self.frame_width,
            self.frame_height,
            self.frame_count,
            self.fps,
            rally_ranges=resolved_ranges,
            use_homography=self.use_homography,
        )
        print(
            f"       Calibration: top={calibration.top:.0f} bottom={calibration.bottom:.0f} "
            f"left={calibration.left:.0f} right={calibration.right:.0f} "
            f"net_y={calibration.net_y:.0f} (from {calibration.samples_used} player samples)"
        )
        if calibration.samples_used == 0:
            print("       WARNING: too few player detections — using generous full-frame fallback")

        detector = ShotDetector(
            frame_height=self.frame_height,
            frame_width=self.frame_width,
            fps=self.fps,
            calibration=calibration,
        )

        print("       Checking for TrackNetV3 shuttle predictions...")
        ball_csv = ensure_ball_predictions(self.video_path)
        shuttle_tracker = ShuttleTracker(ball_csv) if ball_csv else None
        self.shuttle_tracker = shuttle_tracker
        if shuttle_tracker:
            print(f"       Using real shuttle positions from {ball_csv.name}")
        else:
            print(
                "       TrackNetV3 unavailable on this machine — "
                "falling back to player-position proxy (lunge-apex)"
            )

        all_shots: list[Shot] = []
        shots_with_position: list[Shot] = []
        real_shuttle_samples: list[tuple[int, float, float]] = []
        global_shot_number = 1
        previous_winner = 0  # winner of the prior rally serves the next one

        for rally, (start_frame, _end) in zip(rallies, resolved_ranges):
            # First receiver = opponent of whoever served = opponent of the
            # previous rally's winner (badminton rule: rally winner serves
            # next). The very first rally of the match has no prior winner
            # to derive this from — that's a coin toss we can't observe, so
            # it falls back to a single documented default, not a per-rally
            # answer key.
            if previous_winner in (1, 2):
                first_receiver = 3 - previous_winner
            else:
                first_receiver = 2  # default for the match's first rally only

            print(
                f"       Rally {rally.score_sequence}: "
                f"frames {start_frame}-{rally.end_frame} (first_receiver=player {first_receiver})..."
            )

            shots = detector.detect_shots_in_rally(
                self.cap,
                start_frame,
                rally.end_frame,
                rally.score_sequence,
                first_receiver=first_receiver,
            )

            # Assign zones using the receiving player's lunge-apex position
            # (most-extended point in a window around the shot, not a single
            # fixed frame — see player_detector.find_lunge_apex). The window
            # is capped by neighboring shots so it can't bleed into the next
            # reach-and-recover arc.
            shot_frames = [s.frame_idx for s in shots]
            for i, shot in enumerate(shots):
                prev_frame = shot_frames[i - 1] if i > 0 else start_frame
                next_frame = shot_frames[i + 1] if i < len(shots) - 1 else rally.end_frame
                window_before = min(LUNGE_APEX_WINDOW_FRAMES, (shot.frame_idx - prev_frame) // 2)
                window_after = min(LUNGE_APEX_WINDOW_FRAMES, (next_frame - shot.frame_idx) // 2)

                pos = None
                is_real_shuttle = False
                if shuttle_tracker:
                    pos = shuttle_tracker.landing_point(prev_frame, shot.frame_idx)
                    is_real_shuttle = pos is not None
                if pos is None:
                    pos = detector.estimate_shuttle_position_apex(
                        self.cap, shot.frame_idx, shot.receive_by, window_before, window_after
                    )
                if pos:
                    shot.shuttle_x, shot.shuttle_y = pos
                    _half, zone = calibration.zone_for(pos[0], pos[1])
                    shot.zone = zone
                    shots_with_position.append(shot)
                    if is_real_shuttle:
                        real_shuttle_samples.append(
                            (shot.receive_by, float(pos[0]), float(pos[1]))
                        )

                shot.shot_number = global_shot_number
                global_shot_number += 1

            all_shots.extend(shots)
            print(f"         -> {len(shots)} shots detected")

            if rally.winner > 0:
                previous_winner = rally.winner

        # Second pass: the calibration above derives top/bottom/net_y from
        # player FEET, which don't reach as far toward the baseline as the
        # shuttle itself does — visually confirmed to place the back-row
        # boundary just a few pixels from the real baseline, off the actual
        # court surface (see docs/RESULTS.md "Court Calibration Variants").
        # Now that real shuttle landing positions exist, recompute the row
        # bounds from those directly and re-map every shot's zone through
        # the corrected calibration.
        recalibrated = recalibrate_from_shuttle_positions(calibration, real_shuttle_samples)
        if recalibrated is not calibration:
            print(
                f"       Recalibrated row bounds from {len(real_shuttle_samples)} real "
                f"shuttle positions: top={recalibrated.top:.0f} bottom={recalibrated.bottom:.0f} "
                f"net_y={recalibrated.net_y:.0f}"
            )
            for shot in shots_with_position:
                _half, zone = recalibrated.zone_for(shot.shuttle_x, shot.shuttle_y)
                shot.zone = zone
        else:
            print(
                "       Too few real shuttle positions to recalibrate row bounds — "
                "keeping player-position calibration"
            )

        self.calibration = recalibrated

        print(f"       Total shots: {len(all_shots)}")
        return all_shots

    def _build_shot_output(
        self, rallies: list[Rally], all_shots: list[Shot]
    ) -> list[dict]:
        """Build the per-shot output data with last-shot logic applied.

        Rules:
        - last_receive = "yes" for the final shot in each rally
        - If last receiver != point winner → out = "no" (shuttle was IN)
        - If last receiver == point winner → out = "yes" (shuttle was OUT)
        """
        # Group shots by score_sequence
        shots_by_rally: dict[int, list[Shot]] = {}
        for shot in all_shots:
            if shot.score_sequence not in shots_by_rally:
                shots_by_rally[shot.score_sequence] = []
            shots_by_rally[shot.score_sequence].append(shot)

        # Build rally winner lookup
        rally_winners: dict[int, int] = {}
        for rally in rallies:
            if rally.winner > 0:
                rally_winners[rally.score_sequence] = rally.winner

        output = []
        for shot in all_shots:
            rally_shots = shots_by_rally.get(shot.score_sequence, [])
            is_last = shot == rally_shots[-1] if rally_shots else False
            winner = rally_winners.get(shot.score_sequence, 0)

            if is_last and winner > 0:
                last_receive = "yes"
                # Apply badminton rules for out/in determination
                if shot.receive_by == winner:
                    out = "yes"  # Receiver got the point → shuttle was OUT
                else:
                    out = "no"  # Receiver didn't get point → shuttle was IN
                win_by = f"player {winner}"
            else:
                last_receive = "n/a"
                out = "n/a"
                win_by = "n/a"

            output.append({
                "shot_number": shot.shot_number,
                "match": 1,
                "score_sequence": shot.score_sequence,
                "sequence_in_rally": shot.sequence_in_rally,
                "receive_by": f"player {shot.receive_by}",
                "zone": shot.zone,
                "last_receive": last_receive,
                "out": out,
                "win_by": win_by,
            })

        return output

    def _render_debug_outputs(self) -> None:
        """Visual QA / debug tooling (Phase F, docs/PRD_v2.4.md).

        Diagnostic-only: draws the court grid, player foot markers,
        best-effort racket boxes, and shuttle position (when TrackNetV3 has
        data for that frame) onto sampled screenshots and/or a full debug
        video. Reuses the calibration/shuttle-tracker/rally-range state
        `_detect_shots` already computed rather than recomputing anything.
        """
        if self.cap is None or self.calibration is None:
            return

        if self.debug_frames:
            frame_indices = sample_frame_indices(self._resolved_ranges, self.debug_frames)
            out_dir = DEBUG_FRAMES_FOLDER / self.video_path.stem
            out_dir.mkdir(parents=True, exist_ok=True)
            print(f"       Saving {len(frame_indices)} sampled debug frames to {out_dir}")
            for frame_idx in frame_indices:
                frame = self._read_frame(frame_idx)
                if frame is None:
                    continue
                annotated = self._annotate_frame(frame, frame_idx)
                cv2.imwrite(str(out_dir / f"frame_{frame_idx:06d}.png"), annotated)

        if self.debug_video:
            DEBUG_VIDEO_FOLDER.mkdir(parents=True, exist_ok=True)
            out_path = DEBUG_VIDEO_FOLDER / f"{self.video_path.stem}_annotated.mp4"
            print(f"       Rendering annotated debug video to {out_path}")
            self._render_debug_video(out_path)

    def _read_frame(self, frame_idx: int):
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = self.cap.read()
        return frame if ret else None

    def _annotate_frame(self, frame, frame_idx: int):
        players = detect_players(frame)
        rackets = detect_rackets(frame)
        shuttle = self.shuttle_tracker.at_frame(frame_idx) if self.shuttle_tracker else None
        return draw_overlays(frame, self.calibration, players, rackets, shuttle)

    def _render_debug_video(self, out_path: Path) -> None:
        """Renders only the analyzed rally windows, not the whole video
        (replays/crowd shots between rallies aren't useful to visually QA
        and would triple the encoding cost for no diagnostic value).
        """
        fourcc = cv2.VideoWriter_fourcc(*"mp4v")
        writer = cv2.VideoWriter(
            str(out_path), fourcc, self.fps, (self.frame_width, self.frame_height)
        )
        try:
            for start, end in self._resolved_ranges:
                self.cap.set(cv2.CAP_PROP_POS_FRAMES, start)
                frame_idx = start
                while frame_idx < end:
                    ret, frame = self.cap.read()
                    if not ret:
                        break
                    writer.write(self._annotate_frame(frame, frame_idx))
                    frame_idx += 1
        finally:
            writer.release()


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Badminton video analysis pipeline")
    parser.add_argument(
        "video_path", nargs="?",
        help="Path to input .mp4 (defaults to the first .mp4 found in input/)",
    )
    parser.add_argument(
        "--debug-frames", nargs="?", type=int,
        const=DEFAULT_DEBUG_FRAME_SAMPLE_COUNT, default=None, metavar="N",
        help=(
            "Save N randomly-sampled annotated frame screenshots (court grid, "
            f"player foot, best-effort racket, shuttle) to {DEBUG_FRAMES_FOLDER}/. "
            f"Defaults to N={DEFAULT_DEBUG_FRAME_SAMPLE_COUNT} if the flag is given "
            "with no value. Off by default — diagnostic tooling only "
            "(docs/PRD_v2.4.md Phase F)."
        ),
    )
    parser.add_argument(
        "--debug-video", action="store_true",
        help=(
            f"Render a full annotated debug video to {DEBUG_VIDEO_FOLDER}/, covering "
            "the analyzed rally windows. Off by default — diagnostic tooling only "
            "(docs/PRD_v2.4.md Phase F)."
        ),
    )
    parser.add_argument(
        "--homography", action="store_true",
        help=(
            "Use the real court-line homography (bird's-eye, perspective-correct "
            "zone mapping) as the primary zone coordinate system, falling back to "
            "the proportional pixel-space grid for points outside the detected "
            "court quadrilateral. Off by default pending broader validation across "
            "more videos (see docs/RESULTS.md)."
        ),
    )
    return parser.parse_args(argv)


def main() -> None:
    """CLI entry point."""
    args = _parse_args(sys.argv[1:])

    # Determine video path
    if args.video_path:
        video_path = Path(args.video_path)
    else:
        # Look for videos in the input folder
        INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        videos = list(INPUT_FOLDER.glob("*.mp4"))
        if not videos:
            print(f"No MP4 files found in {INPUT_FOLDER}/")
            print("Usage: python -m src.main <video_path> [--debug-frames [N]] [--debug-video]")
            print(f"   or: place an MP4 file in the '{INPUT_FOLDER}/' folder")
            sys.exit(1)
        video_path = videos[0]
        if len(videos) > 1:
            print(f"Multiple videos found, processing: {video_path.name}")

    # Ensure output folder exists
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    try:
        pipeline = AnalysisPipeline(
            video_path,
            debug_frames=args.debug_frames,
            debug_video=args.debug_video,
            use_homography=args.homography,
        )
        output_path = pipeline.run()
        print(f"\nAnalysis complete!")
        print(f"Results saved to: {output_path}")
    except ValidationError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Analysis failed: {e}")
        raise


if __name__ == "__main__":
    main()

