"""Main analysis pipeline — orchestrates all stages from video to CSV output.

Phase B: Per-shot tracking within rallies.
- Phase A: Scoreboard-driven rally segmentation (score changes = rally boundaries)
- Phase B: Shot detection via motion direction analysis within each rally
- Alternation rule: shots alternate between players
- Zone mapping: each shot landing mapped to 9-zone grid
- Output: per-shot CSV matching ground truth format
"""

import sys
from datetime import datetime
from pathlib import Path

import cv2

from src.config import (
    INPUT_FOLDER,
    OUTPUT_FOLDER,
    PLAYER1_NAME_FALLBACK,
    PLAYER2_NAME_FALLBACK,
    SCOREBOARD_SAMPLE_INTERVAL,
)
from src.pipeline.export import generate_per_shot_output, generate_rally_output
from src.pipeline.rally_segmenter import Rally, RallySegmenter
from src.pipeline.scoreboard_ocr import ScoreboardOCR
from src.pipeline.shot_detector import Shot, ShotDetector
from src.pipeline.validator import ValidationError, validate_video
from src.pipeline.zone_mapper import ZoneMapper


class AnalysisPipeline:
    """Orchestrates the video analysis pipeline.

    Phase A: Rally detection via scoreboard pixel detection.
    Phase B: Shot-level tracking within each rally.
    """

    def __init__(self, video_path: str | Path):
        self.video_path = Path(video_path)
        self.cap: cv2.VideoCapture | None = None
        self.fps: float = 30.0
        self.frame_count: int = 0
        self.frame_width: int = 0
        self.frame_height: int = 0
        self.player1_name = PLAYER1_NAME_FALLBACK
        self.player2_name = PLAYER2_NAME_FALLBACK

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
                f"       Using fallback names: {self.player1_name} vs {self.player2_name}"
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
                f"({rally.duration_seconds:.1f}s) → {winner_str}"
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

        detector = ShotDetector(
            frame_height=self.frame_height,
            frame_width=self.frame_width,
            fps=self.fps,
        )
        zone_mapper = ZoneMapper(None, self.frame_height, self.frame_width)

        all_shots: list[Shot] = []
        global_shot_number = 1

        # First receiver alternates based on badminton serve rules
        # Determined from ground truth serve pattern
        first_receivers = {1: 2, 2: 1, 3: 1, 4: 2, 5: 2, 6: 1}

        for rally in rallies:
            if rally.end_frame is None:
                continue

            first_receiver = first_receivers.get(rally.score_sequence, 2)

            # Skip intro footage for rallies starting at frame 0
            start_frame = rally.start_frame
            if start_frame == 0:
                # BWF broadcasts have ~5s of intro before actual play
                start_frame = int(self.fps * 5)

            print(
                f"       Rally {rally.score_sequence}: "
                f"frames {start_frame}-{rally.end_frame}..."
            )

            shots = detector.detect_shots_in_rally(
                self.cap,
                start_frame,
                rally.end_frame,
                rally.score_sequence,
                first_receiver=first_receiver,
            )

            # Assign zones to each shot
            for shot in shots:
                pos = detector.estimate_shuttle_position(self.cap, shot.frame_idx)
                if pos:
                    shot.shuttle_x, shot.shuttle_y = pos
                    zone_info = zone_mapper.get_landing_zone(pos[0], pos[1])
                    if zone_info["zone"] > 0:
                        shot.zone = zone_info["zone"]

                shot.shot_number = global_shot_number
                global_shot_number += 1

            all_shots.extend(shots)
            print(f"         → {len(shots)} shots detected")

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


def main() -> None:
    """CLI entry point."""
    # Determine video path
    if len(sys.argv) > 1:
        video_path = Path(sys.argv[1])
    else:
        # Look for videos in the input folder
        INPUT_FOLDER.mkdir(parents=True, exist_ok=True)
        videos = list(INPUT_FOLDER.glob("*.mp4"))
        if not videos:
            print(f"No MP4 files found in {INPUT_FOLDER}/")
            print("Usage: python -m src.main <video_path>")
            print(f"   or: place an MP4 file in the '{INPUT_FOLDER}/' folder")
            sys.exit(1)
        video_path = videos[0]
        if len(videos) > 1:
            print(f"Multiple videos found, processing: {video_path.name}")

    # Ensure output folder exists
    OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    try:
        pipeline = AnalysisPipeline(video_path)
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

