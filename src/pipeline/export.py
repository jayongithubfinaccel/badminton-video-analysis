"""CSV output generation — produce per-shot analysis results.

Generates CSV output matching the ground truth template format:
No, match, score, Sequence of shot, receive by, zone (receive by),
last receive?, out?, win by
"""

from pathlib import Path

import pandas as pd

from src.pipeline.rally_segmenter import Rally


def generate_rally_output(
    rallies: list[Rally],
    output_path: Path,
    player1_name: str = "Player 1",
    player2_name: str = "Player 2",
) -> Path:
    """Generate Phase A rally-level CSV output.

    At this phase, we output one row per rally (score sequence) showing
    the detected boundaries and winners.
    """
    rows = []
    for rally in rallies:
        row = {
            "score_sequence": rally.score_sequence,
            "start_frame": rally.start_frame,
            "end_frame": rally.end_frame,
            "start_time_sec": round(rally.start_time, 2),
            "end_time_sec": round(rally.end_time, 2) if rally.end_time else None,
            "duration_sec": round(rally.duration_seconds, 2),
            "winner": f"player {rally.winner}" if rally.winner > 0 else "partial",
            "change_type": rally.change_type,
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Write as CSV
    csv_path = output_path.with_suffix(".csv")
    df.to_csv(csv_path, index=False)

    return csv_path


def generate_per_shot_output(
    shot_data: list[dict],
    output_path: Path,
    player1_name: str = "Player 1",
    player2_name: str = "Player 2",
) -> Path:
    """Generate per-shot CSV output matching ground truth format.

    Each row represents a single shot (shuttle exchange).
    """
    rows = []
    for shot in shot_data:
        row = {
            "": "",  # Empty first column (matches ground truth)
            "No": shot["shot_number"],
            "match": shot.get("match", 1),
            "score": shot["score_sequence"],
            "Sequence of shot": shot["sequence_in_rally"],
            "receive by": shot["receive_by"],
            "zone (receive by)": shot["zone"],
            "last receive?": shot["last_receive"],
            "out?": shot["out"],
            "win by": shot["win_by"],
        }
        rows.append(row)

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    csv_path = output_path.with_suffix(".csv")
    df.to_csv(csv_path, index=False)

    return csv_path


def generate_output(
    results: list[dict],
    output_path: Path,
    player1_name: str = "Player 1",
    player2_name: str = "Player 2",
) -> Path:
    """Legacy output generator (Excel format). Kept for compatibility."""
    rows = []
    for point in results:
        row = {
            "No": point["point_number"],
            "Point Winner": player1_name if point["winner"] == 1 else player2_name,
            "Game": point["game"],
            f"{player1_name} Score": point["player1_score"],
            f"{player2_name} Score": point["player2_score"],
            "Rally Shot Count": point.get("rally_shot_count", 0),
        }

        for z in range(1, 10):
            row[f"P1-Z{z}"] = point.get("player1_zones", {}).get(z, 0)

        row[f"{player1_name} Win/Lose Zone"] = point.get("player1_final_zone", "")

        for z in range(1, 10):
            row[f"P2-Z{z}"] = point.get("player2_zones", {}).get(z, 0)

        row[f"{player2_name} Win/Lose Zone"] = point.get("player2_final_zone", "")
        row["Confidence"] = point.get("confidence", 0.0)

        rows.append(row)

    df = pd.DataFrame(rows)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(output_path, index=False, sheet_name="Match Analysis")

    return output_path
