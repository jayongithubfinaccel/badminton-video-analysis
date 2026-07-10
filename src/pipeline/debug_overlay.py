"""Visual debug overlay drawing (Phase F, docs/PRD_v2.4.md).

Draws the 9-zone court grid, player foot markers, best-effort racket boxes,
and the shuttlecock position onto a single frame. One pure, stateless
function backs both the sampled-screenshot tool and the full annotated
debug video (see frame_sampler.py and main.py's _render_debug_outputs), so
the two never draw differently.

Diagnostic-only: nothing here feeds back into shot detection, zone mapping,
or CSV output generation.
"""

import cv2
import numpy as np

from src.pipeline.court_calibration import CourtCalibration
from src.pipeline.player_detector import PlayerBox, RacketBox
from src.pipeline.zone_grid import zone_for_bands

_GRID_COLOR = (0, 255, 255)  # yellow (BGR)
_FOOT_COLOR = (0, 0, 255)  # red
_RACKET_COLOR = (255, 0, 255)  # magenta
_SHUTTLE_COLOR = (0, 255, 0)  # green


def draw_overlays(
    frame: np.ndarray,
    calibration: CourtCalibration,
    player_boxes: list[PlayerBox] | None = None,
    racket_boxes: list[RacketBox] | None = None,
    shuttle_point: tuple[float, float] | None = None,
) -> np.ndarray:
    """Return a COPY of frame with all requested overlays drawn.

    Any of player_boxes/racket_boxes/shuttle_point may be None/empty —
    missing signals are simply skipped, not treated as an error (a shuttle
    is frequently undetected; see docs/PRD_v2.4.md Phase F scope).
    """
    out = frame.copy()
    _draw_court_grid(out, calibration)

    for box in player_boxes or []:
        x, y = box.foot_point
        cv2.drawMarker(
            out, (int(x), int(y)), _FOOT_COLOR,
            markerType=cv2.MARKER_TRIANGLE_UP, markerSize=16, thickness=2,
        )

    for box in racket_boxes or []:
        cv2.rectangle(
            out, (int(box.x1), int(box.y1)), (int(box.x2), int(box.y2)),
            _RACKET_COLOR, 2,
        )

    if shuttle_point is not None:
        x, y = shuttle_point
        cv2.drawMarker(
            out, (int(x), int(y)), _SHUTTLE_COLOR,
            markerType=cv2.MARKER_STAR, markerSize=14, thickness=2,
        )

    return out


def _draw_court_grid(frame: np.ndarray, cal: CourtCalibration) -> None:
    """Draw both players' 3x3 zone grids, the net line, and zone number
    labels at each cell's center.
    """
    top, bottom, left, right, net_y = cal.top, cal.bottom, cal.left, cal.right, cal.net_y

    cv2.rectangle(frame, (int(left), int(top)), (int(right), int(bottom)), _GRID_COLOR, 2)
    cv2.line(frame, (int(left), int(net_y)), (int(right), int(net_y)), _GRID_COLOR, 2)

    col_edges = [left + f * (right - left) for f in (0.0, 1 / 3, 2 / 3, 1.0)]
    top_row_edges = [top + f * (net_y - top) for f in (0.0, 1 / 3, 2 / 3, 1.0)]
    bottom_row_edges = [net_y + f * (bottom - net_y) for f in (0.0, 1 / 3, 2 / 3, 1.0)]

    for x in col_edges[1:-1]:
        cv2.line(frame, (int(x), int(top)), (int(x), int(bottom)), _GRID_COLOR, 1)
    for y in top_row_edges[1:-1] + bottom_row_edges[1:-1]:
        cv2.line(frame, (int(left), int(y)), (int(right), int(y)), _GRID_COLOR, 1)

    for half, row_edges in (("top", top_row_edges), ("bottom", bottom_row_edges)):
        for row in range(3):
            # row is in screen top-to-bottom order within this half's band
            # list. For "top", row 0 (nearest the frame's top edge) is
            # already nearest that half's own baseline. For "bottom",
            # row 0 (nearest net_y, since bottom_row_edges starts there) is
            # nearest the NET, so it must be flipped to net_axis_band's
            # "0 = own baseline" convention before calling zone_for_bands.
            net_axis_band = row if half == "top" else (2 - row)
            for col in range(3):
                zone = zone_for_bands(net_axis_band, col, half)
                cx = int((col_edges[col] + col_edges[col + 1]) / 2)
                cy = int((row_edges[row] + row_edges[row + 1]) / 2)
                cv2.putText(
                    frame, str(zone), (cx - 6, cy + 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, _GRID_COLOR, 1, cv2.LINE_AA,
                )
