# Deployment Log

Chronological record of every meaningful deployment/push to `main`. Newest entries at the top.

Entry format:
```
## YYYY-MM-DD — <short title>
- **Changes**: what shipped
- **Tests**: what was run/added and the result (pass/fail, coverage of new logic)
- **Manual verification**: what was exercised by hand, if anything
- **Follow-ups**: anything left to do
```

---

## 2026-07-03 — Fix back-row/mid-row zone collapse via shuttle-derived row recalibration
- **Changes**: `_detect_shots()` in `src/main.py` now runs a second calibration pass after shot detection. Root cause (found via a visual audit overlaying the calibrated grid, YOLO boxes, and TrackNetV3 shuttle points on real frames): the row-axis bounds (`top`/`bottom`/`net_y`) were derived from player-FOOT positions, which don't reach as far toward the baseline as the shuttle does — on video 1 this placed the back-row/mid-row boundary only ~3px from the real baseline, so nearly the entire "back row" zone band fell off the actual court surface, and any real back-court shot got bucketed as "mid." Added `recalibrate_from_shuttle_positions()` (`src/pipeline/court_calibration.py`) which re-derives `top`/`bottom`/`net_y` from the 5th/95th percentile of *real* TrackNetV3 shuttle landing Y-values (not the lunge-apex proxy) once shots are known, leaving `left`/`right` (column axis) untouched since that axis was already well-fit. Parameters (percentile pair, outward margin, blend-with-original alpha) were chosen via a sweep against video 1's ground truth. A second variant explored during investigation (hybrid: homography-derived row + proportional column) was tested, found to underperform the chosen approach, and removed rather than left half-wired.
- **Tests**: Added `tests/test_court_calibration.py` (6 new unit tests covering `recalibrate_from_shuttle_positions`: too-few-samples fallback, percentile/margin formula correctness, left/right and metadata pass-through, homography clearing, alpha=0 no-op, and exclusion of malformed `receive_by` values). `pytest` — 6/6 pass. `ruff check` clean on all touched files (3 pre-existing, unrelated lint issues remain elsewhere in `main.py` — unused import, an f-string without placeholders, one over-length line — not touched, to keep this change scoped).
- **Manual verification**: Ran the full pipeline end-to-end on both test videos (`python -m src.main`, real YOLO + TrackNetV3, no mocks).
  - Video 1 vs ground truth (70 shots/6 rallies, n=53 matched by rally+position): zone exact-match 13.2%→**17.0%**, zone exact-or-adjacent 60.4%→**64.2%**, row-distribution divergence from ground truth 0.528→**0.340** (back/mid/front moved from 17.0/47.2/35.8 to 18.9/37.7/43.4 vs true 34.0/20.8/45.3), column-axis divergence unchanged at 0.038 (confirms the fix is row-only, as designed).
  - Video 2 (no ground truth, plausibility check): front-row share went from 2.4% (baseline — front zones were nearly erased) to **37.8%**, now spread across 8 of 9 zones instead of collapsing into 2-3.
- **Follow-ups**: Not a complete fix — zone-exact-or-adjacent still well under the PRD's 80% target, and the tuning sweep found configs with even higher adjacent-accuracy (67.9%) that were rejected because they cost row-fit; further iteration on the row-axis signal (rather than more hybrid combinations with homography, which was tried and didn't help) is the likely next lever. Separately, the same investigation surfaced an unrelated bug worth a follow-up: rally 1's current 6-second intro-skip is too short — a static tournament-title graphic at t=9.8s was processed as live rally footage.

---

## 2026-07-03 — Initialize CLAUDE.md and deployment tracking
- **Changes**: Added `CLAUDE.md` (repo/workflow guidance) and this deployment log. No application code changed.
- **Tests**: N/A (documentation only)
- **Manual verification**: N/A
- **Follow-ups**: Backfill this log isn't required for prior commits (Phase A–D, YOLO tracking, court calibration, shuttle tracking via TrackNetV3) since they predate this policy — start logging from the next deployment forward.
