"""Input validation for video files."""

import os
from pathlib import Path

from src.config import MAX_DURATION_MINUTES, MAX_FILE_SIZE_MB, SUPPORTED_FORMATS


class ValidationError(Exception):
    pass


def validate_video(video_path: str | Path) -> Path:
    """Validate video file meets requirements. Returns resolved Path."""
    path = Path(video_path).resolve()

    if not path.exists():
        raise ValidationError(f"File not found: {path}")

    if path.suffix.lower() not in SUPPORTED_FORMATS:
        raise ValidationError(
            f"Only MP4 format supported. Got: {path.suffix}"
        )

    file_size_mb = os.path.getsize(path) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValidationError(
            f"File exceeds {MAX_FILE_SIZE_MB}MB limit. Size: {file_size_mb:.1f}MB"
        )

    # Check duration using OpenCV
    import cv2

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise ValidationError(f"Cannot open video file: {path}")

    fps = cap.get(cv2.CAP_PROP_FPS)
    frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
    cap.release()

    if fps <= 0:
        raise ValidationError("Cannot determine video FPS.")

    duration_minutes = (frame_count / fps) / 60
    if duration_minutes > MAX_DURATION_MINUTES:
        raise ValidationError(
            f"Video exceeds {MAX_DURATION_MINUTES}-minute limit. "
            f"Duration: {duration_minutes:.1f} minutes"
        )

    return path
