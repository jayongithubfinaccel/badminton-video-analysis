"""Canonical 9-zone numbering for a badminton court half.

The single source of truth for "given a position within one player's court
half, what zone number is that" — shared by the proportional-grid path
(court_calibration.zone_for), the homography path (court_detector's
court_coords_to_zone), and the visual debug overlay (debug_overlay.py).

This used to be three separate, near-identical implementations. That
duplication is exactly how a real bug survived four phases (Phase C through
the 2026-07-03 zone-collapse fix) without being caught: each copy correctly
reversed the row order between halves (so "back row" always numbers 1-3 and
"front row" 7-9 regardless of which half), but none of them reversed the
COLUMN order for the "top" half — see docs/PRD_v2.5.md for the discovery and
fix writeup.

Per badminton_court_9zone.png (this project's reference image), the two
halves are mirror images of each other, not simple repeats, because of how
a single elevated broadcast camera sees them:
  - The near/bottom player is seen from behind (camera looks the same
    direction they face), so on-screen-left IS their own left — no mirror.
  - The far/top player faces the camera (we see their front), so
    on-screen-left is their own RIGHT — column order must be reversed.

Reference layout (screen left-to-right, per row):
    top half:    back row (near baseline) = 3, 2, 1
                 mid row                  = 6, 5, 4
                 front row (near net)     = 9, 8, 7
    ---------------------------- NET ----------------------------
    bottom half: front row (near net)     = 7, 8, 9
                 mid row                  = 4, 5, 6
                 back row (near baseline) = 1, 2, 3

Two row-banding functions live here, deliberately not one:

- `_band()` — plain equal-thirds. Used for the column axis always (there is
  no official badminton line that splits the court width into thirds — only
  the center line, which splits it in half for serving), and for the row
  axis of the *proportional pixel-space* fallback grid
  (court_calibration.CourtCalibration.zone_for's non-homography path). That
  fallback's "0.0-1.0" range is the observed spread of player foot
  positions, not the true court boundary, so imposing exact real-court-line
  fractions on it would assert a precision the underlying measurement
  doesn't have.
- `_row_band_real()` — real BWF service-line fractions. Used for the row
  axis only when the 0.0-1.0 range genuinely IS true court-plane distance
  (net to baseline), i.e. the homography path
  (court_detector.court_coords_to_zone). There, "equal thirds" was a
  placeholder that doesn't match how the court is actually marked: the
  front zone (7/8/9) should end at the short service line, close to the
  net, and the back zone (1/2/3) should start at the long service line,
  close to the baseline — see docs/PRD_v2.6.md.
"""

# Standard BWF court dimensions (Laws of Badminton), one player's half:
#   net to back boundary line (half-court depth): 670 cm  (COURT_LENGTH/2
#     in court_detector.py — duplicated here as a bare ratio, not imported,
#     to keep this module dependency-free; see module docstring)
#   short service line, measured from the net:      198 cm
#   long service line (doubles), measured from the
#     back boundary line:                            76 cm
# These are fixed physical constants of the sport, not a per-video tuned
# value — the same fractions apply to every video; only the homography
# (fit per-video from that video's own detected court corners) changes.
_HALF_COURT_DEPTH_CM = 670.0
_SHORT_SERVICE_LINE_FROM_NET_CM = 198.0
_LONG_SERVICE_LINE_FROM_BASELINE_CM = 76.0

# net_axis_frac thresholds (0.0 = own baseline, 1.0 = net) implied by the
# real line positions above.
FRONT_BAND_FRAC = 1.0 - _SHORT_SERVICE_LINE_FROM_NET_CM / _HALF_COURT_DEPTH_CM
BACK_BAND_FRAC = _LONG_SERVICE_LINE_FROM_BASELINE_CM / _HALF_COURT_DEPTH_CM


def _band(frac: float) -> int:
    """Bucket a 0-1 fraction into band 0 (first third), 1 (middle third), or
    2 (last third). Clamps out-of-range input rather than raising, matching
    this project's existing zone-mapping clamp behavior for off-court points.
    """
    frac = max(0.0, min(1.0, frac))
    return 0 if frac < 1 / 3 else (1 if frac < 2 / 3 else 2)


def _row_band_real(frac: float) -> int:
    """Bucket a 0-1 net_axis_frac into back(0)/mid(1)/front(2) using the
    real BWF short/long service line positions instead of equal thirds —
    see module docstring for why this one isn't just `_band()`.
    """
    frac = max(0.0, min(1.0, frac))
    return 0 if frac < BACK_BAND_FRAC else (1 if frac < FRONT_BAND_FRAC else 2)


def zone_for_bands(net_axis_band: int, side_axis_band: int, half: str) -> int:
    """Zone number (1-9) for a cell already expressed as (row band, column
    band), each 0-2.

    net_axis_band: 0 = nearest this half's own baseline (back row), 2 =
        nearest the net (front row) — same meaning for both halves.
    side_axis_band: 0 = on-screen-left, 2 = on-screen-right — raw screen
        position, NOT yet adjusted for which way the player is facing.
    half: "top" (far/camera-facing player) or "bottom" (near player).

    This is the one place the on-screen-left/right -> player's-own-left/
    right mirror is applied. Every caller should go through here (or
    zone_number below) rather than re-deriving row*3+col+1 locally.
    """
    col = (2 - side_axis_band) if half == "top" else side_axis_band
    return net_axis_band * 3 + col + 1


def zone_number(net_axis_frac: float, side_axis_frac: float, half: str) -> int:
    """Zone number (1-9) for a position expressed as two 0-1 fractions,
    using equal-thirds banding on both axes.

    net_axis_frac: 0.0 at this half's own baseline, 1.0 at the net.
    side_axis_frac: 0.0 at the court's on-screen left edge, 1.0 at the
        on-screen right edge — raw screen position; mirroring for the
        player's own perspective is handled internally (see
        zone_for_bands).
    half: "top" or "bottom".

    Used by the proportional pixel-space fallback grid. For real court-plane
    coordinates (the homography path), use `zone_number_real` instead — see
    module docstring for why the row axis differs between the two.
    """
    return zone_for_bands(_band(net_axis_frac), _band(side_axis_frac), half)


def zone_number_real(net_axis_frac: float, side_axis_frac: float, half: str) -> int:
    """Zone number (1-9) for a position expressed as two 0-1 fractions of
    TRUE court-plane distance (e.g. from a homography), using the real BWF
    short/long service line positions for the row axis instead of equal
    thirds. Column axis stays equal-thirds (see module docstring — there's
    no official line that splits the width into thirds).
    """
    return zone_for_bands(_row_band_real(net_axis_frac), _band(side_axis_frac), half)
