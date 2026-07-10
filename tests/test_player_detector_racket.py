"""Tests for RacketBox (Phase F) — the dataclass only, not live YOLO
inference (detect_rackets() itself requires the actual yolov8n.pt model and
is exercised via manual end-to-end runs, not unit tests, same as
detect_players()).
"""

from src.pipeline.player_detector import RacketBox


def test_center_is_midpoint_of_box():
    box = RacketBox(x1=100.0, y1=50.0, x2=140.0, y2=90.0, confidence=0.2)
    assert box.center == (120.0, 70.0)


def test_center_handles_zero_area_box():
    box = RacketBox(x1=10.0, y1=10.0, x2=10.0, y2=10.0, confidence=0.15)
    assert box.center == (10.0, 10.0)
