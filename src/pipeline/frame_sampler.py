"""Seeded random frame sampling within rally windows (Phase F, docs/PRD_v2.4.md).

Used by the --debug-frames CLI flag to pick a small, representative set of
frames to screenshot with overlays, without re-scanning the whole video or
picking frames from between-rally footage (replays/crowd shots/scoreboard-
only frames), which would waste the sample budget on non-court content.
"""

import random


def sample_frame_indices(
    rally_ranges: list[tuple[int, int]],
    count: int,
    seed: int = 0,
) -> list[int]:
    """Return up to `count` frame indices sampled from within rally_ranges.

    Sampling is proportional to each rally's length (a longer rally
    contributes more candidate frames, so it isn't under-represented) and
    seeded for reproducibility across repeated runs on the same video.
    Returns fewer than `count` indices if the combined rally frame span is
    smaller than `count`, and an empty list if rally_ranges is empty or
    count <= 0.
    """
    if count <= 0:
        return []

    all_frames = []
    for start, end in rally_ranges:
        all_frames.extend(range(start, end))

    if not all_frames:
        return []

    rng = random.Random(seed)
    k = min(count, len(all_frames))
    return sorted(rng.sample(all_frames, k))
