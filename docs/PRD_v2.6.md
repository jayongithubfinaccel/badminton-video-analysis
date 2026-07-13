# Badminton Video Analysis Service — PRD v2.6

> **Version:** 2.6 — Real-World Court Geometry for the 9-Zone Grid
> **Status:** Active
> **Author:** Jayson Fetra
> **Date:** 10 July 2026 (Phase G.5 added 12 July 2026; Phase G.6 ground-truth re-validation added 12 July 2026)
> **Platform:** Backend Python service (CLI)
> **Supersedes:** PRD v2.4

---

## 0. What Changed in v2.6

This revision does **not** change the product goals or scored output pipeline shape (Sections 1–5, 7, 8 are unchanged from v2.4 except where explicitly noted below). It adds one new phase — **Phase G: Real-court-geometry zone mapping** — covering four related pieces of work, done in this order:

1. **Validated the homography-based zone mapping, with the proportional grid as a fallback, as the proposed default** (not yet flipped on by default in `main.py` — still opt-in via `--homography` pending broader multi-video validation). This revisits Phase C.1's 2026-06-27 decision to disable homography for zone mapping: that decision was about a *player-foot-position proxy* carrying a monocular height bias into the homography, not about homography's geometric correctness — and it predates Phase D's real shuttle tracking. Re-tested against video 1's ground truth with real shuttle positions: homography roughly halves row/column distributional divergence vs. the shipped proportional grid, at the cost of coverage (a homography-only point can fall outside the detected court quadrilateral) — which the existing-but-previously-disabled fallback path in `CourtCalibration.zone_for()` already covers. Full writeup and numbers: `docs/reports/court_zone_homography_vs_proportional.html`; a real re-run of the pipeline showing the grid, and player/racket/shuttle tracking together: `docs/reports/court_zone_homography_example_video1.html`.
2. **Replaced equal-thirds row banding with the real BWF short/long service line positions, for the homography path only.** The front-zone (7/8/9) boundary now sits at the short service line (198cm from the net) and the back-zone (1/2/3) boundary at the long service line (76cm from the back boundary) — not at 1/3 and 2/3 of the half-court depth. The proportional pixel-space fallback grid's row axis is deliberately **left as equal-thirds** — its 0–1 range is an observed-player-position box, not true court-plane distance, so imposing exact real-line fractions on it would assert a precision that measurement doesn't have. See `zone_grid.py`'s module docstring for the full reasoning.
3. **Added white-line-based corner refinement** (`court_detector.refine_corners_with_lines`) to correct the green-playing-surface-derived corners (which can run a little short of, or a little past, the actual painted boundary line) against the real detected white lines, with a conservative, fallback-safe design — see Section 9, Phase G.3.
4. **Answered "should court-box prediction use a trained model instead of a formula?"** (Section 9, Phase G.4): no, not yet — the "camera angle changes the box proportions" problem this idea was raised to solve is already what homography solves (it's a per-video-fit perspective transform, not a fixed box); a trained keypoint-detection model would only be justified if line-detection-based corner refinement (G.3) proves insufficiently robust across many more videos than the two this project currently has.
5. **Adjusted the back-zone boundary based on visual review of the deployed G.1–G.3 output** (Section 9, Phase G.5): the literal long-service-line boundary (76cm deep) read as too shallow for "deep court" shot placement once seen rendered on real frames. The back zone (1/2/3) now starts further forward — mid (4/5/6) shrunk 20% and that depth was handed to back; front (7/8/9), still the short-service-line boundary, is untouched.

None of this is wired into the default (no-flag) pipeline output yet — the CSV output shape and default zone-mapping method (`use_homography=False`) are unchanged. This document proposes flipping the default in a future phase once G.1–G.3 (and now G.5) have been validated across more than two videos.

---

## 1. Overview

*(Unchanged from v2.4 — see PRD_v2.4.md Section 1.)*

This is a **backend-only Python service** that automatically analyzes badminton singles match video from broadcast footage and produces **per-shot structured data** — one row for every shuttle exchange in the match. The user places an MP4 video file in an input folder, runs the service, and receives a CSV output file where each row represents a single shot. No frontend. No manual annotation. Fully automated via computer vision.

---

## 2. Problem Statement

*(Unchanged from v2.4.)*

---

## 3. Goals and Non-Goals

*(Unchanged from v2.4, with one addition to 3.1:)*

### 3.1 Goals (addition)

- **Map each shot's landing position to the 9-zone court grid using the court's actual physical geometry** (real BWF service-line positions via homography) where a validated per-video homography exists, falling back to the existing proportional grid otherwise — rather than treating "divide the court into thirds" as correct by construction *(new in v2.6)*.

### 3.2 Non-Goals (v2.6 addition)

- No training or deployment of a dedicated court-keypoint ML model in this phase — see Phase G.4's reasoning for why the formula-based approach is tried first.
- No change to doubles-vs-singles court width handling — `COURT_WIDTH` remains the doubles width (610cm); this phase only changes the row (net-to-baseline) axis.

---

## 4. Badminton Rules Context

*(Unchanged from v2.4.)*

### 4.5 Court Line Dimensions (new in v2.6)

Standard BWF court dimensions relevant to zone mapping (one player's half, net to back boundary line = 670cm = half of the full 13.4m court length):

| Line | Distance | Measured from |
|---|---|---|
| Short service line | 198 cm | the net |
| Long service line (doubles) | 76 cm | the back boundary line (baseline) |

These fixed physical constants (not per-video tuned values) originally defined the front/mid/back row-zone boundaries for the homography coordinate path — see Phase G.2. **Updated in Phase G.5**: the back boundary is no longer the literal long service line — see below.

| Zone boundary | Depth from net | Basis |
|---|---|---|
| Front / mid (7-9 vs 4-6) | 198 cm | Literal short service line — unchanged since G.2 |
| Mid / back (4-6 vs 1-3) | 514.8 cm | **G.5 adjustment**: literal long-service-line depth (594cm) minus 20% of the literal mid-band depth (396cm × 0.20 = 79.2cm), moved net-ward — not the literal long service line itself |

The mid band (short service line to the mid/back boundary) is 316.8cm — 20% shallower than its literal 396cm BWF span — and the back band is 155.2cm, roughly double its literal 76cm span. Front is unchanged at 198cm.

---

## 5. Input Specifications

*(Unchanged from v2.4.)*

---

## 6. Output Specifications

*(Unchanged from v2.4 except 6.5 below.)*

### 6.5 Zone Definition (9-Zone Court Grid) — updated in v2.6

Zone numbering itself is unchanged (Z1–Z3 back, Z4–Z6 mid, Z7–Z9 front, mirrored columns on the far/top half — see `zone_grid.py`, `badminton_court_9zone.png`). What's new in v2.6 is that **the row-band boundaries are no longer necessarily equal thirds**:

```
                    BASELINE (back)
    ┌───┬───┬───┐   ─┐
    │ 1 │ 2 │ 3 │    │ back band: 155.2cm (G.5-adjusted — starts well before
    ├───┼───┼───┤   ─┤                     the literal long service line)
    │ 4 │ 5 │ 6 │    │ mid band: 316.8cm (short service line to the
    │   │   │   │    │  G.5-adjusted back boundary) — still the largest band
    ├───┼───┼───┤   ─┤
    │ 7 │ 8 │ 9 │    │ front band: 198cm (net to short service line, unchanged)
    └───┴───┴───┘   ─┘
          NET
```

- **When a validated per-video homography exists** (`CourtCalibration.homography` is set): row bands use the real BWF line positions above, with the Phase G.5 back-band adjustment (`zone_grid.zone_number_real`, `court_detector.court_coords_to_zone`). Column bands remain equal-thirds — there is no official line dividing the court width into thirds (only the center line, which splits it in half for serving).
- **Otherwise** (the proportional pixel-space fallback, fit from observed player positions): both axes remain equal-thirds (`zone_grid.zone_number`), unchanged from v2.4. Applying the real-line fractions to a player-position-derived box would misrepresent that box as true court-plane distance, which it isn't.

---

## 7. Technical Architecture

*(Unchanged from v2.4 except the additions below.)*

### 7.2 Required Capabilities (addition)

| Stage | Capability | Purpose |
|-------|-----------|---------|
| 3a. Homography Refinement *(new, v2.6)* | Snap green-surface corner estimates to detected white boundary lines | Correct both overshoot (green threshold bleeding past the true line) and undershoot (green mat running short of it) before computing the homography |

### 7.3 Folder Structure (addition)

```
badminton-video-analysis/
├── docs/
│   ├── PRD_v2.6.md            # this document
│   └── reports/                # (new, v2.6) saved HTML investigation reports
│       ├── court_zone_homography_vs_proportional.html
│       └── court_zone_homography_example_video1.html
├── src/pipeline/
│   ├── zone_grid.py            # (updated, v2.6) adds zone_number_real / _row_band_real (BWF lines)
│   ├── court_detector.py       # (updated, v2.6) adds refine_corners_with_lines; court_coords_to_zone uses zone_number_real
│   └── debug_overlay.py        # (updated, v2.6) draws the real homography trapezoid (BWF row bands) when a homography is active, not just the proportional rectangle
├── tests/
│   └── test_court_detector.py  # (new, v2.6) BWF row-banding + corner-refinement coverage
```

### 7.4 Generalization & Anti-Hardcoding Requirements (addition)

| Current state | Where | Note |
|---|---|---|
| Real BWF service-line distances (198cm, 76cm) are fixed constants | `zone_grid.py` | **Not** a per-video hardcode in the sense Section 7.4 warns against — these are universal physical constants of the sport (same on every court in the world), analogous to `COURT_WIDTH`/`COURT_LENGTH` already in `court_detector.py`. What varies per video is the homography itself (fit from that video's own detected corners), which is what maps these fixed real-world fractions onto that video's specific pixel geometry. |
| `--homography` CLI flag defaults to off | `main.py` | Deliberately opt-in pending validation across more than the two videos this project currently has (see Phase G.1) — flipping a zone-mapping default based on n=2 videos would repeat the exact mistake Section 7.4 already documents elsewhere in this project's history. |

---

## 8. Configuration

*(Unchanged from v2.4, with one CLI addition:)*

```
--homography    # opt-in: use real court-line homography (BWF row bands) as
                 # the primary zone coordinate system, falling back to the
                 # proportional grid for off-court points. Off by default.
```

---

## 9. Iteration Plan

*(Phases A–F unchanged from v2.4 — see PRD_v2.4.md.)*

### Phase G — Real-Court-Geometry Zone Mapping (2026-07-10)

**Goal:** Make the 9-zone court grid track the badminton court's actual physical geometry (true perspective, true service-line proportions, true boundary lines) instead of a proportional pixel-space approximation, and decide whether that requires a trained model or can be done with a formula.

#### G.1 — Homography as the primary zone-mapping method, proportional grid as fallback

**Motivation:** Phase C.1 (2026-06-27) disabled homography for zone mapping after finding it made predictions *worse* — but the input signal at the time was a player's foot position used as a shuttle-landing proxy, and the failure mechanism identified was specifically the monocular height bias of mapping a *standing person's* foot through a ground-plane homography. Phase D (2026-06-29) replaced that proxy with real TrackNetV3 shuttle positions, which don't have a person's-height bias — but no one had re-tested homography against the *new* signal. This phase does.

**Method:** Re-ran the full pipeline on video 1 (rally segmentation → shot detection → real TrackNetV3 shuttle positions, unchanged) and scored the same 53 ground-truth-matched shuttle positions three ways:

| Method | Coverage | Exact | Exact-or-adjacent | Row divergence | Col divergence |
|---|---|---|---|---|---|
| A — shipped proportional grid (recalibrated) | 100% | 15.1% | 66.0% | 0.340 | 0.226 |
| B — homography only, no fallback | 85% | 15.6% | 62.2% | **0.178** | **0.178** |
| C — hybrid (homography, proportional fallback) | 100% | 13.2% | 60.4% | 0.226 | 0.189 |

*(Row/col divergence = sum of absolute differences between predicted and true back/mid/front and left/center/right shot-share distributions; lower is better. Exact/adjacent move within noise at n=53; divergence is the steadier signal.)*

Generalization check on video 2 (no ground truth zones, coverage only): homography-only coverage dropped to 50.6% (vs 85% on video 1) — different camera framing makes corner detection noisier on some videos. The hybrid (Method C) still reaches 100% coverage there, which is why it — not homography-only — is the proposed method.

**Visual validation:** the homography-projected trapezoid grid (`court_detector.detect_court_corners` + `compute_homography`, both already implemented since Phase C.1, just not wired into zone-lookup by default) tracks the real sidelines/net/service lines closely on in-play frames of both videos, matching the two hand-drawn ground-truth grid images almost exactly. See `docs/reports/court_zone_homography_vs_proportional.html` for the side-by-side images, and `docs/reports/court_zone_homography_example_video1.html` for a full pipeline re-run with player/racket/shuttle tracking overlaid on the homography grid.

**Real bug found and fixed as a result of testing this end-to-end:** `recalibrate_from_shuttle_positions()` (the Phase D-followup second calibration pass) unconditionally cleared the homography field on its output. With `--homography` enabled, every shot's zone would have silently reverted to the plain proportional grid immediately after this second pass ran — before a single shot's zone was ever actually looked up through the homography. Fixed to preserve homography (only the fallback bounds are refined by this pass); test updated (`test_preserves_homography_on_the_recalibrated_result`, formerly asserted the opposite).

**Decision:** kept `--homography` opt-in (not the default) — see 7.4's addition above. The debug/diagnostic overlay (`debug_overlay.py`) was fixed to actually draw the homography trapezoid when active (previously it always drew the proportional rectangle regardless), since showing the wrong grid shape would make this feature impossible to visually QA.

#### G.2 — Real BWF service-line row banding (replacing equal thirds)

**Motivation:** raised directly by user feedback reviewing G.1's demo screenshots: the front/mid boundary should sit at "the white line closest to the net" (the short service line) and the mid/back boundary should sit "closer to the white line in the back" (the long service line) — not at arbitrary equal-thirds points that don't correspond to any painted line.

**Method:** Section 4.5's real distances (198cm from net, 76cm from baseline, over a 670cm half-court depth) give two `net_axis_frac` cut points — `FRONT_BAND_FRAC ≈ 0.7045`, `BACK_BAND_FRAC ≈ 0.1134` at the time this phase was first implemented — used in place of 1/3 and 2/3. This produced asymmetric bands (front 29.5% of depth, mid 59.1%, back 11.3%) instead of equal 33/33/33. **`BACK_BAND_FRAC` was subsequently revised in Phase G.5 below** (front and the underlying `FRONT_BAND_FRAC` are unchanged).

**Scope decision:** applied only to the homography coordinate path (`court_detector.court_coords_to_zone`, via the new `zone_grid.zone_number_real`), **not** the proportional pixel-space fallback (`court_calibration.zone_for`'s non-homography branch, still `zone_grid.zone_number`, unchanged). The fallback's 0–1 range is an empirically observed player-position box, not verified true court-plane distance — asserting exact real-line fractions on it would claim a precision that measurement doesn't have. The column axis stays equal-thirds on both paths — there's no official line splitting the court width into thirds (only the center line, which splits it in half for serving).

**Validation:** `tests/test_zone_grid.py` (new banding-threshold tests, a test confirming the bands are asymmetric and BWF-derived, and a test confirming a point that would classify differently under equal-thirds vs. the real bands actually does); `tests/test_court_detector.py` (new — covers `court_coords_to_zone` at the real line boundaries for both halves). `debug_overlay._draw_homography_grid`'s drawn lines were updated to the same asymmetric fractions so the visual overlay can't drift out of sync with what `zone_for()` actually computes.

#### G.3 — White-line-based corner refinement

**Motivation:** also raised in the same user feedback: the drawn court boundary should be derived from the actual white lines, and shouldn't exceed the real court boundary. Zooming into generated debug frames confirmed a real, visible gap between the homography-projected boundary and the true white sideline on some corners (in the direction of the green mat's own extent running short of the painted line, not the direction of overshoot at those particular corners — both directions are possible depending on the frame, per `court_detector.py`'s corner-detection docstring history).

**Method:** `court_detector.refine_corners_with_lines(frame, corners)` — takes the existing green-mask-derived coarse corners, runs the already-implemented (but previously unused for this) `detect_court_lines()` Hough-segment detector, and for each of the 4 coarse edges: finds Hough segments matching that edge by angle (within 12°) and proximity (within 15% of the edge's own length), fits a single line to their combined endpoints (`cv2.fitLine`), and re-intersects adjacent fitted lines for a boundary-accurate corner. Falls back to the coarse corner (per-edge, or entirely) whenever fewer than 2 of 4 edges get a confident match, or a refined corner would move more than 12% of the quadrilateral's average edge length from the coarse estimate — a bad line match (e.g. snapping to a service line instead of the baseline) degrades to the pre-refinement behavior rather than silently producing something worse.

**Wired into:** `calibrate_homography()`, immediately after `detect_court_corners()` and before the existing `bot_w >= top_w` sanity check (so the sanity check runs on the refined, more accurate corners).

**Validation:** `tests/test_court_detector.py` — a synthetic white-rectangle-on-green frame with the coarse corners deliberately shifted outward by 12px on every edge; refinement recovers a mean corner error under 3px (vs the 12px it started with). Two fallback-safety tests: a blank frame with no lines returns the coarse corners unchanged; a coarse estimate implausibly far from any detected line (simulating a bad upstream detection) is also left unchanged rather than being "corrected" toward a plausible-looking but unverified answer.

**Honest read:** validated on synthetic data with clean, thick, unambiguous lines. Not yet re-validated end-to-end against the two real ground-truth videos' actual corner-detection accuracy (that would need the same visual-overlay + coverage methodology as G.1, repeated with refinement on); flagged as the concrete next step before considering G.3 done, not silently assumed to transfer.

#### G.4 — Should court-box prediction use a trained model instead of a formula?

**Question raised:** "the court boxes length is the same for all courts even though due to camera angle, ideally the court boxes will not have the same length — is it better to use a model to predict the court boxes?"

**Answer: not yet, and probably not first.** Two separate problems were being described together, and they have two different fixes already in this phase:

1. **"Different camera angle should produce different box proportions in pixel space"** — this is exactly what the homography (G.1) already does. The equal-thirds *pixel-space* grid (the proportional fallback) is the one thing that can't adapt to camera angle, by construction — it's a flat proportional split of a bounding box. The homography grid, by contrast, is a per-video-fit perspective transform: the same real-world 198cm/76cm line positions get projected to *different* pixel positions on every video, automatically matching that video's specific camera angle/zoom/framing (confirmed visually in G.1 — the projected trapezoid's proportions visibly differ between video 1 and video 2's generated overlays). No model is needed to solve this specific problem; it was already solved by adopting real-world coordinates as the reference frame, the same reasoning that motivated using homography at all.
2. **"Court corner/line detection itself is sometimes imprecise"** — this is the real remaining gap (G.3's motivation), and IS a place where a trained model (e.g. a court-keypoint-detection network, analogous to how TrackNetV3 was adopted for the shuttle in Phase D rather than hand-rolling motion heuristics) could plausibly do better than the current color-threshold-plus-Hough-lines approach, especially on courts with unusual lighting, mat colors, or camera framing this project's two test videos haven't exposed. But that's a meaningfully heavier lift than G.3 (requires either a pretrained checkpoint that generalizes to this domain, or training data this project doesn't have) and isn't yet justified by evidence — G.3's classical-CV refinement hasn't even been stress-tested against more than synthetic data yet (see G.3's honest-read note).

**Recommendation:** ship and validate G.1–G.3 first (formula + refined classical CV), across more videos than the two currently available, before investing in a trained keypoint model. Revisit this question specifically if/when corner-detection failure rate (tracked via `calibrate_homography`'s own `num_valid_samples` return value, already logged) proves to be a recurring problem across a wider video sample — that would be the concrete, evidence-based trigger to justify the model-training cost, not a decision to make on n=2 videos.

#### G.5 — Back-band adjustment: mid shrunk 20%, back zone extended forward (2026-07-12)

**Motivation:** raised by user visual review of the G.1–G.3 deployed output (fresh screenshots off the real pipeline run, `docs/reports/` — see the confirmation-run review artifact from the 2026-07-11 deployment). The literal long-service-line boundary put the back zone (1/2/3) at just a 76cm-deep strip — visually, this read as too shallow for how a viewer judges "deep court" shot placement against real broadcast footage. Front (7/8/9, the short service line boundary) looked correct as-is and was explicitly left alone.

**Method:** shrink the mid band's depth by a fixed 20% and hand the freed depth to the back band, leaving the front/mid boundary (short service line, 198cm from net) untouched:

- Literal BWF mid depth (short service line to long service line): 396cm
- New mid depth: 396 × (1 − 0.20) = 316.8cm
- New back depth: 670 − 198 (front) − 316.8 (mid) = 155.2cm (vs. the literal 76cm)
- `BACK_BAND_FRAC` updated from ≈0.1134 to 155.2/670 ≈ **0.2316**; `FRONT_BAND_FRAC` unchanged at ≈0.7045

This is implemented as an explicit, traceable adjustment in `zone_grid.py` (`_MID_BAND_SHRINK_FRAC = 0.20`), not a silently-hardcoded replacement fraction — the module keeps the literal BWF mid depth (`_MID_DEPTH_CM_BWF`) alongside the adjusted value so the derivation is auditable from the source. A fixed fraction applied identically to every video (not a per-video tuned value), same posture as the original BWF constants.

**Scope:** homography path only, same as G.2 — the proportional pixel-space fallback's row axis is still equal-thirds and untouched by this adjustment, for the same reason given in G.2 (its 0–1 range isn't verified true court-plane distance).

**Validation:** `tests/test_zone_grid.py::test_band_fracs_are_asymmetric_and_bwf_derived` updated to assert the new `BACK_BAND_FRAC` value and that it's larger than the literal long-service-line fraction. `tests/test_court_detector.py` rewritten to derive its expected y-coordinates from `BACK_BAND_FRAC`/`FRONT_BAND_FRAC` directly (rather than hardcoding depths) so it can't silently drift out of sync if these constants are tuned again, plus two new cases confirming a point 100cm from the baseline — past the literal long service line but inside the new adjusted back band — now correctly classifies as back (previously would have been mid). `debug_overlay._draw_homography_grid` needed no code change since it already reads `BACK_BAND_FRAC`/`FRONT_BAND_FRAC` as shared constants — the drawn grid picks up the new boundary automatically. `pytest` — 66/66 pass after the change (13 tests touched/added across this phase in total).

**Honest read:** this is a qualitative adjustment from visual review, not re-validated against video 1's ground-truth CSV numerically — Section 12's divergence/coverage metrics for G.1 predate this change and haven't been re-measured with G.5 applied. That combined re-measurement (G.2 + G.3 + G.5 together, against ground truth) is still the open item from G.1/G.2 (see Section 13, Q8), now slightly larger in scope.

#### G.6 — Combined re-validation against ground truth (2026-07-12): a real trade-off, not a clean win

**Motivation:** Q8/Q10 both asked for exactly this — re-measure the deployed method (G.1 hybrid + G.2 BWF banding + G.3 corner refinement + G.5 back-band adjustment, all together, as `--homography` actually behaves) against video 1's ground-truth CSV, rather than relying on the pre-G.3/G.5 numbers in Section 12.

**Method:** ran the real `AnalysisPipeline` twice (`use_homography=False` and `True`) end-to-end and scored the same 53 ground-truth-matched shots three ways, same methodology as G.1:

| Method | Coverage | Exact | Exact-or-adjacent | Row divergence | Col divergence |
|---|---|---|---|---|---|
| A — shipped proportional grid | 100% | 15.1% | 66.0% | 0.340 | 0.226 |
| B — homography-only, no fallback (refined corners, G.5 bands) | 84.9% | 13.3% | 66.7% | 0.444 | 0.178 |
| C — `--homography` hybrid, **as actually deployed** | 100% | 11.3% | 64.2% | **0.453** | **0.151** |

Versus the G.1-era hybrid numbers (equal-thirds rows via homography, no corner refinement): exact 13.2%→11.3% (slightly worse), adjacent 60.4%→64.2% (slightly better), **col divergence 0.189→0.151 (better)**, **row divergence 0.226→0.453 (roughly doubled — worse)**.

**Two separate effects, opposite directions:**

1. **Column accuracy genuinely improved** (0.189→0.151), most plausibly from G.3's corner refinement making the homography's left/right mapping more accurate. A clean win with no apparent trade-off.
2. **Row accuracy got substantially worse.** The actual row distributions explain why:

   | | back | mid | front |
   |---|---|---|---|
   | Ground truth | 34.0% | 20.8% | 45.3% |
   | Method C (now) | 26.4% | 43.4% | 30.2% |

   G.5 made mid (4/5/6) the largest zone by geometric depth (~47% of half-court depth), matching the real service-line proportions. But this match's actual shot placement doesn't distribute that way — real rallies cluster shots near the net and near the baseline, not mid-court (true mid share is only 20.8%). A geometrically larger mid band absorbs more shots that are visually closer to front or back, which is exactly what happened: mid is now over-predicted by more than 2x, pulled from both front and back.

**Honest read:** the back zone looks more visually correct against real footage (which is what motivated G.5), but that same change measurably hurts row-distribution accuracy against this ground truth. This isn't a case of "the code is broken" — exact/adjacent-match are roughly stable — it's a genuine tension between matching the court's real physical markings and matching how shots actually distribute in a real match. Not resolved as of this writing; see Section 13, Q8/Q10 (updated) for the decision still pending.

---

## 10. Acceptance Criteria (Overall)

*(AC-01 through AC-16 unchanged from v2.4 — see PRD_v2.4.md. Addition:)*

| ID | Criterion |
|----|-----------|
| AC-17 *(new, v2.6)* | With `--homography` enabled: `CourtCalibration.zone_for()` uses real BWF service-line row bands (not equal thirds) whenever a validated homography is active, and falls back to the equal-thirds proportional grid — never an unclassified/crashing result — for any point outside the detected court quadrilateral. |
| AC-18 *(new, v2.6)* | `refine_corners_with_lines()` never produces a *worse* (further from the true boundary) quadrilateral than its input coarse corners — enforced by the max-shift-fraction fallback, covered by synthetic tests in `test_court_detector.py`. |

---

## 11. Risks and Mitigations

*(Unchanged from v2.4, with one addition:)*

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Homography-only coverage varies a lot by video (85% on video 1, 50.6% on video 2) | A pure homography rollout would silently lose over half of video 2's shots to "no zone" | Hybrid fallback (G.1, already implemented) guarantees 100% coverage on every video regardless of corner-detection reliability for that specific camera framing |
| White-line corner refinement (G.3) only validated on synthetic data so far | Could look correct in unit tests but not actually improve (or could regress) real-video corner accuracy | Flagged explicitly as the next validation step (G.3 honest-read note) before relying on it; not claimed as validated beyond synthetic coverage |

---

## 12. Success Metrics

*(Phase A–F rows unchanged from v2.4. New row:)*

| Metric | Phase G Target | Status after G.6 combined re-measurement |
|---|---|---|
| Zone row/col distributional divergence (video 1, vs. shipped proportional grid) | Lower on both axes | **Partially met.** Col: met (0.226→0.151, hybrid). Row: **not met** — 0.226→0.453 (hybrid), worse than the shipped proportional grid's own 0.340. See G.6. |
| Coverage (fraction of shots a method can classify at all) | 100% for whatever method ships as default | Met — hybrid (Method C) is 100% on video 1; homography-only alone is not (84.9%/50.6% across the two videos) |

**Current measured state (video 1, n=53):** see the G.6 table (supersedes the G.1-only table previously here). The combined G.2+G.3+G.5 re-measurement is done — it reveals a real row-accuracy regression from G.5, not a clean improvement across the board. This is the concrete reason `--homography` remains opt-in (Section 13, Q8) rather than a reason to consider the phase finished.

---

## 13. Open Questions

*(Questions 1–7 unchanged from v2.4. New:)*

| # | Question | Proposed Answer |
|---|----------|----------------|
| 8 *(resolved, G.6)* | Should `--homography` become the default (rather than opt-in)? | **No, decided.** The combined re-measurement (G.6) showed column accuracy improved (0.189→0.151) but row accuracy regressed (0.226→0.453, worse than even the shipped proportional grid's 0.340) — a real, known cost, kept deliberately (see Q10). Opt-in remains the right posture until/unless the row-axis question is revisited. |
| 9 *(new)* | Is the corner-refinement approach (G.3, classical CV) sufficient long-term, or will it eventually need a trained keypoint model? | Not decided — see G.4. Tracked via `calibrate_homography`'s existing `num_valid_samples` return value; a recurring low-sample-count pattern across many videos would be the concrete trigger to revisit. |
| 10 *(resolved, G.6)* | Is the G.5 back-band adjustment (20% mid shrink) the right amount, or just a first pass? | **Decided 2026-07-12: keep it as-is.** Confirmed it moves row divergence in the wrong direction (0.226→0.453 vs ground truth) — a real, measured cost, not a hunch. Kept anyway for visual/product reasons (the back zone reading correctly against real footage was the point of the change); the row-accuracy cost is accepted, not overlooked. Not reverted, not retuned. |
| 11 *(new, 2026-07-13)* | Should rally 1's 6-second intro-skip be lengthened, now that the per-shot audit re-confirmed it's too short (4 of 55 shots land on ceremony footage)? | Not decided — this predates Phase G entirely (flagged 2026-07-03) and is out of scope for court-zone-mapping work specifically, but it's now visibly costing this video's own ground-truth accuracy numbers (those 4 shots can't possibly score correctly). Worth fixing on its own merits independent of anything else in this PRD. |

---

## 14. Reference Data

*(14.1–14.3 unchanged from v2.4. Addition:)*

### 14.4 Phase G Reports (new in v2.6)

| Report | Contents |
|---|---|
| `docs/reports/court_zone_homography_vs_proportional.html` | Method comparison (homography vs. proportional grid), visual grid-vs-ground-truth comparison on both videos, the G.1 metrics table |
| `docs/reports/court_zone_homography_example_video1.html` | Full pipeline re-run example: frame screenshots and a video clip showing the homography grid tracking players/racket/shuttle live |
| `docs/reports/phase_g_deploy_review.html` | Fresh confirmation-run screenshots after the initial Phase G deploy |
| `docs/reports/phase_g5_before_after_review.html` | Same frames, before/after the G.5 back-band adjustment — visual confirmation the boundary actually moved |
| `docs/reports/both_videos_frame_review.html` | Frame review across both ground-truth videos on the deployed code |
| `docs/reports/ground_truth_per_shot_comparison.html` | **G.6 supporting detail**: all 53 ground-truth-matched shots, each with the exact frame used for zone mapping, predicted vs. true zone, and result (exact/adjacent/miss) — filterable by result. Source of the ceremony-frame finding below. |
| `docs/results/csv/` | Latest per-shot analysis CSVs (both videos), `--homography` enabled |
| `docs/results/gt_comparison_frames_video1/` | The 53 individual annotated frame images backing the per-shot comparison report, plus `records.json` (full per-shot data: rally, sequence, receiver, predicted/ground-truth zone, result, source frame) |

**New finding from building the per-shot report (2026-07-13), not previously documented:** rally 1's first 4 shots (frames 180–294, ~6–10s into the video) land on pre-match ceremony/coin-toss footage, not real rally play — their "ground truth miss" is a data-quality artifact, not a zone-mapping error. Root cause: the already-known, previously-flagged issue that rally 1's 6-second intro-skip is too short for this video (see the 2026-07-03 `DEPLOYMENT_LOG.md` entry, "Follow-ups") — this per-shot audit is what made it visible again, not a new bug from this phase. Not fixed as part of this work; flagged as a candidate follow-up (see Section 13).

---

## 15. Decision Log

*(Entries through 2026-07-09 unchanged from v2.4. New entries:)*

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-07-10 | Re-tested homography for zone mapping using real TrackNetV3 shuttle positions instead of the player-foot proxy that motivated disabling it in Phase C.1 | The original rejection mechanism (monocular height bias of a standing person's foot) doesn't apply to a shuttle's ground-contact point; the underlying geometry was never re-tested against the corrected signal until now. |
| 2026-07-10 | Kept the homography+fallback hybrid, not homography alone, as the proposed method | Homography-only coverage varies too much by video (85% / 50.6%) to be safe as a sole method; the already-implemented fallback path gives 100% coverage on both. |
| 2026-07-10 | Fixed `recalibrate_from_shuttle_positions()` to preserve homography instead of clearing it | With homography enabled, every shot's zone would have silently reverted to the plain proportional grid right after this pass ran, defeating the point of enabling it at all — found by tracing the pipeline end-to-end while building the demo, not by code review alone. |
| 2026-07-10 | Replaced equal-thirds row banding with real BWF short/long service line fractions, for the homography path only (not the proportional fallback) | User feedback: the front/mid and mid/back boundaries should track actual painted lines, not arbitrary thirds. Scoped to homography only because the proportional fallback's 0–1 range isn't verified true court-plane distance — applying exact line fractions there would be unjustified precision. |
| 2026-07-10 | Added white-line-based corner refinement (`refine_corners_with_lines`), fallback-safe by design | User feedback: the drawn court boundary should reference the actual white lines and not exceed the real court. Made conservative (falls back per-edge or entirely on low confidence) so it can't make corner accuracy worse than doing nothing. |
| 2026-07-10 | Decided against training a court-keypoint ML model for now | The specific problem raised ("camera angle should change box proportions") is already solved by adopting homography (a per-video real-world coordinate fit); a trained model would only be justified for the separate problem of corner-detection robustness, which hasn't yet been stress-tested enough (n=2 videos) to justify the cost. |
| 2026-07-12 | Shrunk the mid band 20% and gave that depth to the back band (`BACK_BAND_FRAC` ≈0.1134 → ≈0.2316), leaving front unchanged | User visual review of deployed G.1–G.3 output on real frames: the literal 76cm long-service-line back band read as too shallow for "deep court" placement; front looked correct as-is. Scoped to the homography path only, same reasoning as G.2. Not yet re-validated against ground-truth metrics — qualitative visual call, flagged as such (Q10). |
| 2026-07-12 | Ran the combined G.2+G.3+G.5 re-measurement against ground truth (G.6) — found a real row-divergence regression (0.226→0.453), not a clean win | Q10's visual call was correct about *looking* more like real footage, but wrong about improving row-distribution accuracy against this match's actual shot placement (which clusters front/back, not mid-court, unlike the geometrically-larger mid band G.5 produces). Column accuracy did genuinely improve (0.189→0.151), most likely from G.3's corner refinement. Left `--homography` opt-in and G.5 code unchanged pending an explicit decision on the trade-off (Q8/Q10 updated) — not silently reverted or kept. |
| 2026-07-12 | Decided to keep G.5 (mid-shrink/back-band adjustment) despite the measured row-divergence regression | Explicit product call: visual correctness against real footage (the back zone reading as genuinely deep) was worth more than this specific ground-truth row-distribution metric. `--homography` stays opt-in (Q8) — this decision doesn't change that posture, since the row-axis cost is real and unresolved either way. |
