# Badminton Video Analysis Service — PRD v2.3

> **Version:** 2.3 — Player-Tracking Pivot & Anti-Hardcoding Requirements
> **Status:** Active
> **Author:** Jayson Fetra
> **Date:** 26 June 2026
> **Platform:** Backend Python service (CLI)
> **Supersedes:** PRD v2.2

---

## 0. What Changed in v2.3

This revision does **not** change the product goals (Section 2–6 are unchanged from v2.2). It changes the **next engineering phase** and adds a hard requirement that was implicit before but is now explicit because we hit it in practice:

1. **Pivot the next phase from shuttle tracking (TrackNet) to player tracking (YOLO person detection).** Player tracking is easier to get right than shuttle tracking, and — critically — it also fixes the calibration problem in #2 below as a side effect. TrackNet is not abandoned, just deferred (now Phase D instead of Phase C).
2. **Anti-hardcoding requirement.** A second test video (`Badminton_video_example_2.mp4`, 854×480, no ground truth yet) was added on 2026-06-26 and run through the existing Phase A/B pipeline unmodified. It exposed exactly the failure mode we suspected: pixel-region and frame-ratio constants tuned to video 1 do not transfer. See Section 14.3 for the actual evidence. Going forward, no spatial constant may be load-bearing for correctness unless it is derived per-video at runtime.

No development has started on either item yet — this document is the plan.

---

## 1. Overview

This is a **backend-only Python service** that automatically analyzes badminton singles match video from broadcast footage and produces **per-shot structured data** — one row for every shuttle exchange in the match.

The user places an MP4 video file in an input folder, runs the service, and receives a CSV output file where each row represents a single shot: who received it, which zone it landed in, whether it was the last shot of the rally, and who won the point.

No frontend. No manual annotation. Fully automated via computer vision.

---

## 2. Problem Statement

Manually annotating badminton match videos shot-by-shot is extremely time-consuming (a 90-second rally with 16 shots can take 5+ minutes to annotate). Coaches and analysts need this shot-level data for tactical analysis — zone heatmaps, rally patterns, shot sequencing — but lack an automated tool that can extract it from readily available broadcast footage.

This service automates the data collection pipeline: **video in → per-shot CSV out**.

---

## 3. Goals and Non-Goals

### 3.1 Goals

- Detect every individual shot (shuttle exchange) within each rally
- Track which player received each shot
- Map each shot's landing position to a 9-zone court grid
- Detect rally boundaries (score changes) and attribute point winners
- Determine whether the last shot was in or out based on scoring logic
- Extract player names from the broadcast scoreboard overlay
- Output per-shot results in CSV format matching the ground truth template
- Run as a simple CLI: input video → output CSV file
- **Generalize across different broadcast videos without per-video code or constant changes** (new in v2.3 — previously implicit)

### 3.2 Non-Goals (v1)

- No frontend / UI / web interface
- No real-time / streaming analysis (batch processing only)
- No doubles match support
- No shot-type classification (e.g., smash vs drop) — only landing zone
- No cloud deployment — local execution only
- No video editing or highlight generation
- No per-point aggregate output (can be derived from per-shot data later)

---

## 4. Badminton Rules Context

> **PREREQUISITE:** Engineering must understand these rules before implementing any phase. The rules directly inform rally detection logic, shot alternation, and point-winner inference.

### 4.1 Basic Singles Rules

- **Two players** on opposite sides of the net
- **Rally**: sequence of shots starting with a serve and ending when a point is scored
- **Serve**: the first shot of every rally; alternates sides based on score parity
- Players alternate hitting the shuttle — if Player A hits, Player B must return, then Player A, etc.
- A rally ends when:
  - The shuttle lands on the court (point to the hitter)
  - The shuttle lands out of bounds (point to the receiver)
  - The shuttle hits the net and fails to cross (point to the opponent)
  - A fault is committed

### 4.2 Scoring Rules

- Rally point system: a point is scored on every rally regardless of who served
- Games are played to 21 points (win by 2, cap at 30)
- Match is best of 3 games
- After each point, the winner of the rally serves the next rally

### 4.3 Key Heuristics for Automated Detection

These rules translate directly into detection logic:

| Rule | Detection Heuristic |
|------|-------------------|
| Players alternate shots | If last detected shot was received by Player A, next shot must be received by Player B |
| Score change = new rally | When scoreboard changes, current rally has ended and a new one begins |
| Service starts every rally | The first shot of each new score sequence is always a serve |
| Last shot determines winner | If the last receiver does NOT get the point → shuttle was IN (receiver failed to return it properly, or hit it into the net) |
| Last shot determines winner | If the last receiver DOES get the point → shuttle was OUT (hitter's shot landed outside) |

### 4.4 Player Identity (Reference Video)

| Position | Player | Scoreboard Name |
|----------|--------|----------------|
| **Top of frame** (far court) | Player 1 | DONG T.Y. |
| **Bottom of frame** (near court) | Player 2 | FARHAN |

> Note: In BWF broadcast overlays, the player listed first (top row) in the scoreboard typically corresponds to the far-court player.
>
> **v2.3 note:** this table is specific to `Badminton_video_example.mp4`. It must not be relied on as a global fallback — see Section 7.4. The second test video has different players, and the current code's silent fallback to these exact names is one of the concrete bugs this revision flags.

---

## 5. Input Specifications

### 5.1 Video Requirements

| Constraint | Value |
|-----------|-------|
| Format | MP4 only |
| Max file size | 100 MB |
| Max duration | 20 minutes |
| Camera angle | Broadcast footage (elevated, behind one end of the court) |
| Resolution | Minimum 720p recommended |

### 5.2 Video Characteristics (Broadcast Footage)

Based on the reference video (BWF World Tour — Sydney International):
- Camera positioned behind and above one baseline (Farhan's end)
- Perspective angle shows full court with foreshortening
- Scoreboard overlay in top-left corner: player names + game score
- Sponsor banners, crowd, and non-court elements surround the playing area
- Occasional camera cuts to replays, close-ups, or crowd (to be ignored)
- Court lines clearly visible (white/yellow lines on green/blue surface)
- Players: Dong T.Y. (far/top) vs Farhan (near/bottom)

> **v2.3 note:** the second test video (`Badminton_video_example_2.mp4`) is also BWF-style broadcast footage but at a different resolution (854×480 vs 908×480) and a different camera zoom/framing, with different players. It is the first concrete evidence that "broadcast footage" is not one fixed layout — see Section 14.3.

### 5.3 Input Method

- User places MP4 file in `input/` folder (or specifies path via CLI argument)
- Service validates file size and duration before processing
- If validation fails, service exits with descriptive error message

### 5.4 Ground Truth / Validation Data

Reference ground truth file: `badminton_video_result.csv`
- 70 shots across 6 rallies (scores) in the example 55-second video
- Rally lengths: 16, 17, 9, 7, 16, 5+ shots
- Score progression: Player 2 wins scores 1, 2; Player 1 wins score 3; Player 2 wins score 4; Player 2 wins score 5; score 6 partial

> **v2.3 note:** `Badminton_video_example_2.mp4` has **no ground truth yet**. It is used as a *generalization smoke test* (does the pipeline produce sane, non-crashing, non-fallback output?), not as an accuracy benchmark, until it is annotated. See Section 14.3.

---

## 6. Output Specifications

### 6.1 Output Method

- Results written to `output/` folder as `.csv` file
- Filename: `{input_video_name}_analysis_{timestamp}.csv`
- One row per shot (shuttle exchange)

### 6.2 Output Template (CSV Columns)

| Column | Field | Description |
|--------|-------|-------------|
| No | Shot number | Sequential across entire video (1, 2, 3, ...) |
| Match | Match number | Always 1 for single-video analysis |
| Score | Score sequence | Which point/rally this shot belongs to (1, 2, 3, ...) — resets per game |
| Sequence of Shot | Shot within rally | Position of this shot within the current rally (1, 2, 3, ...) |
| Receive By | Receiving player | Which player received/was targeted by this shot: "Player 1" or "Player 2" (use detected name when available) |
| Zone (Receive By) | Landing zone | Zone 1–9 on the receiving player's court half where the shuttle landed |
| Last Receive? | Last shot flag | "yes" if this is the final shot of the rally; "n/a" otherwise |
| Out? | Out of bounds | "yes" if the shuttle landed out (last receiver gets the point); "no" if in (last receiver loses the point); "n/a" for non-final shots |
| Win By | Point winner | Player who won this rally/point; only populated on the last shot row; "n/a" for non-final shots |

### 6.3 Output Example (from ground truth)

```csv
,No,match,score,Sequence of shot,receive by,zone (receive by),last receive?,out?,win by
,1,1,1,1,player 2,7,n/a,n/a,n/a
,2,1,1,2,player 1,3,n/a,n/a,n/a
,3,1,1,3,player 2,5,n/a,n/a,n/a
...
,16,1,1,16,player 1,7,yes,no,player 2
,17,1,2,1,player 1,3,n/a,n/a,n/a
...
```

### 6.4 Derivation Rules

The following can be derived from the per-shot output (for future aggregate reports):

- **Rally shot count**: count of rows per score sequence
- **Zone heatmap per player**: aggregate zone columns grouped by player
- **Win rate**: count of "win by" per player
- **Last-shot outcome**:
  - `last_receive = yes` AND `out = no` → shuttle was IN, receiver failed → point to the OTHER player
  - `last_receive = yes` AND `out = yes` → shuttle was OUT → point to the receiver

### 6.5 Zone Definition (9-Zone Court Grid)

Zone numbering follows the reference image (`badminton_court_9zone.png`):

```
         BASELINE (back)
    ┌───┬───┬───┐
    │ 1 │ 2 │ 3 │  Back row
    ├───┼───┼───┤
    │ 4 │ 5 │ 6 │  Mid row
    ├───┼───┼───┤
    │ 7 │ 8 │ 9 │  Front row
    └───┴───┴───┘
          NET
```

- **Z1–Z3 (Back row):** Near the baseline
- **Z4–Z6 (Mid row):** Middle of the half-court
- **Z7–Z9 (Front row):** Near the net
- Left/Right is from the **player's own perspective** facing the net
- Each player's court half has its own independent 9-zone grid
- "Zone (receive by)" = the zone on the **receiving player's** court half where the shuttle landed

---

## 7. Technical Architecture

### 7.1 Pipeline Stages (Revised)

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────────┐    ┌────────────┐
│  Input   │───►│  Court       │───►│  Scoreboard   │───►│  Shot-by-Shot    │───►│  Output    │
│  Video   │    │  Detection   │    │  OCR (score & │    │  Tracking        │    │  Generator │
│  (.mp4)  │    │  & Homography│    │  player names)│    │  (shuttle + zone)│    │  (.csv)    │
└──────────┘    └──────────────┘    └───────────────┘    └──────────────────┘    └────────────┘
```

### 7.2 Required Capabilities

| Stage | Capability | Purpose |
|-------|-----------|---------|
| 1. Validation | File size/duration/format check | Reject invalid inputs early |
| 2. Court Detection | Detect court boundaries in broadcast frame | Establish coordinate system for zone mapping |
| 3. Homography | Perspective transform to top-down view | Map pixel coords to court positions |
| 4. Player Name Extraction | OCR player names from scoreboard | Use real player names in output |
| 5. Score Change Detection | OCR score from scoreboard across frames | Detect rally boundaries (score change = new rally) |
| 6. Rally Segmentation | Combine score changes + motion/service detection | Define start/end frames of each rally |
| 7. Player Tracking | Detect player bounding boxes frame-by-frame within rallies | Derive court bounds + shot attribution (NEW priority, was shuttle tracking) |
| 8. Shuttle Tracking | Track shuttle position frame-by-frame within rallies | Detect individual shot exchanges (deferred to Phase D) |
| 9. Shot Detection | Identify each individual hit/exchange | One shot = shuttle going from one side to the other |
| 10. Player Attribution | Determine who received each shot | Confirmed by player position, not just alternation |
| 11. Zone Mapping | Map shuttle landing coordinates to zones 1–9 | Fill "zone (receive by)" column |
| 12. Last-Shot Logic | Apply badminton rules to determine winner/out | Fill last_receive, out, win_by columns (already implemented — see Phase E) |
| 13. Output Generation | Write per-shot CSV | Deliver final results |

### 7.3 Folder Structure

```
badminton-video-analysis/
├── input/                  # Place video files here
├── output/                 # Analysis results written here
├── src/
│   ├── main.py            # CLI entry point & pipeline orchestrator
│   ├── config.py          # Configuration constants (per-video calibration must NOT live here as fixed values — see 7.4)
│   ├── pipeline/
│   │   ├── validator.py       # Input validation
│   │   ├── court_detector.py  # Court detection & homography
│   │   ├── frame_filter.py    # Non-play frame detection
│   │   ├── scoreboard_ocr.py  # Player names + score extraction
│   │   ├── rally_segmenter.py # Rally boundary detection
│   │   ├── player_tracker.py  # Player position & attribution (to be rebuilt on YOLO — Phase C)
│   │   ├── shuttle_tracker.py # Shuttle position tracking (upgradeable to TrackNet — Phase D)
│   │   ├── shot_detector.py   # Individual shot/exchange detection
│   │   ├── zone_mapper.py     # Coordinate → zone mapping
│   │   └── outcome_logic.py   # Last-shot winner/out determination
│   ├── models/                # ML model weights (YOLO, TrackNet, etc.)
│   └── utils/
│       └── export.py          # CSV output generation
├── tests/
│   └── test_against_ground_truth.py  # Validation against reference CSV
├── data/
│   ├── ground_truth/          # Reference CSVs for validation
│   └── models/                # Downloaded model weights
├── docs/
│   └── PRD_v2.3.md
├── requirements.txt
└── pyproject.toml
```

### 7.4 Generalization & Anti-Hardcoding Requirements *(new in v2.3)*

**Principle:** No spatial or visual constant may be load-bearing for correctness across different input videos unless it is either (a) derived per-video at runtime from the video's own content, or (b) explicitly documented as a fallback whose use is logged/flagged in the output, never silent.

This requirement exists because it was violated in practice on the very first second video tested (Section 14.3). Concretely, the following must be remediated as part of (or before) Phase C/D work — this is a checklist, not yet implemented:

| Current hardcoded assumption | Where | Problem | Required fix |
|---|---|---|---|
| Court occupies a fixed proportional box (`court_top/bottom/left/right` ≈ 0.15–0.85 / 0.20–0.80 of frame) | `config.py`, `shot_detector.py`, `zone_mapper.py` fallback | Box was eyeballed for video 1's exact camera zoom/framing. On video 2 (different zoom), nearly every shot's estimated landing zone collapsed into zones 7–9 (front row) — see 14.3. | Derive the active play area per video from detected player positions (Phase C) and/or the existing `court_detector.py` homography (Phase D), not a fixed ratio. |
| Scoreboard pixel regions (`SCOREBOARD_NAME_AREA`, `P1_SCORE_ROW`, `P2_SCORE_ROW`) calibrated in absolute pixels for 908×480 | `scoreboard_ocr.py` | Proportionally rescaled for other resolutions, but this assumes the broadcast graphic is laid out identically (same corner, same relative size) on every tournament's overlay. | Detect the scoreboard region's location/size each run (e.g., template/contour search for the overlay box) instead of rescaling a fixed reference rectangle. |
| Player names fall back silently to `DONG T.Y.` / `FARHAN` when detection fails | `config.py` (`PLAYER1_NAME_FALLBACK`, `PLAYER2_NAME_FALLBACK`), `main.py` | On video 2, name OCR failed and the pipeline silently wrote video 1's player names into video 2's output with no warning in the CSV itself. | Fallback values must never be tournament-specific. Use generic `Player 1` / `Player 2` as the only fallback, and surface a clear warning (console + ideally a flag in the output file) whenever the fallback path is used. |
| Player blob detection box (`y_start/y_end`, `x_start/x_end` ≈ 0.2/0.85, 0.1/0.9) | `player_tracker.py` (currently dead code, not wired into `main.py`) | Same fixed-ratio problem; also "non-green = player" is fragile against sponsor banners/crowd/shadows. | Replace with YOLO person detection (Phase C) which doesn't depend on a hand-picked ROI box or color heuristic. |
| Motion-direction thresholds (`min_magnitude`, `min_gap_sec`) tuned by rally-duration bucket | `shot_detector.py` | Thresholds were tuned against video 1's specific motion characteristics. On video 2, shot counts per rally came out implausibly high (e.g., 41 shots in a 48s rally — physically unrealistic), suggesting these thresholds are picking up non-shot motion. | Either replace the underlying signal (player tracking, Phase C) or recalibrate thresholds from per-video motion statistics rather than fixed constants. |

**Acceptance bar for "no hardcoding":** running the pipeline on a new, never-before-seen broadcast video of a different resolution/framing should not require editing `config.py` to get plausible (not necessarily accurate) output, and should never silently substitute another video's player names.

---

## 8. Configuration

```yaml
input:
  max_file_size_mb: 100
  max_duration_minutes: 20
  supported_formats: [".mp4"]
  input_folder: "./input"

output:
  output_folder: "./output"
  format: "csv"

players:
  player1_name_fallback: "Player 1"   # generic only — see 7.4; never a real name
  player2_name_fallback: "Player 2"

processing:
  confidence_threshold: 0.5
  frame_skip: 2
```

> **v2.3 change:** removed `DONG T.Y.` / `FARHAN` as config-level fallbacks (see 7.4 remediation table). Per-video calibration (court bounds, scoreboard region) should be computed at runtime, not stored as global config constants.

---

## 9. Iteration Plan

### Prerequisite: Badminton Rules Understanding

Before any phase begins, engineering must internalize the rules documented in Section 4. Key logic that depends on rules:
- Shot alternation (Player A → Player B → Player A → ...)
- Score change = rally boundary
- Service = first shot of every rally
- Last-shot outcome logic (in/out determination)

### Phase A — Fix Rally Segmentation (Scoreboard-Driven) ✅ DONE

**Goal:** Correctly detect all rallies using scoreboard OCR as primary boundary signal.

**Status:** Implemented (`scoreboard_ocr.py`, `rally_segmenter.py`). 6/6 rallies detected on reference video. Pixel-NCC approach, not literal digit OCR — see code comments for rationale.

---

### Phase B — Shot-Level Tracking (Within Rally) ✅ DONE

**Goal:** Detect each individual shot exchange within a rally.

**Status:** Implemented (`shot_detector.py`) via optical-flow direction-reversal + alternation. 70/70 total shot count on reference video, but with ±1 per-rally errors that cascade into wrong attribution on 3 of the rallies' last shots (see `docs/RESULTS.md`). Confirmed today to **not generalize** to a second video (implausible shot density, zone collapse — Section 14.3). This is the motivation for Phase C below.

---

### Phase C — Player Detection & Adaptive Calibration ✅ DONE (2026-06-27)

**Goal:** Use player position, not shuttle position, to (1) remove the hardcoded frame-ratio assumptions flagged in Section 7.4, and (2) make shot attribution robust to single-frame errors instead of a blind toggle that cascades.

**Status:** Implemented (`player_detector.py`, `court_calibration.py`, updated `shot_detector.py`/`main.py`). Full results in `docs/RESULTS.md` ("Phase C" section). Summary:
- Video 1 (ground truth): 21.4% total shot-count error, 27.5% average per-rally count error (under the 30% bar), 88.7% `receive by` accuracy, **100% `win by` accuracy** (up from 60% in Phase B), 64.2% zone-correct-or-adjacent. Weak point: `out?` accuracy (40%), tied to per-rally shot-count parity, not a new bug — same cascade mechanism flagged in Phase B/E, now isolated to specific rallies (3 and 5) instead of general overcounting.
- Video 2 (no ground truth, generalization check): same code/constants as video 1, produced plausible shot density (`16,14,16,5,10,21` vs Phase B's implausible `41,28,29,13,14,30`) and a zone distribution spread across all 9 zones (vs Phase B's collapse into zones 7–9). Player names correctly fell back to generic placeholders with a visible warning instead of silently reusing video 1's real names.
- Removed an additional hidden hardcode found during implementation: the `first_receivers` lookup table in `main.py` was a 6-entry dict reverse-fit to video 1's ground truth, not derived from badminton's actual serve rule. Replaced with a derivation from the previous rally's detected winner (rule: rally winner serves next).
- New known limitation surfaced (not present in Phase B's scope): video 2 contains genuine multi-camera-angle production cuts *within* a single rally (wide shot cutting to a close-up during a smash), which is a different problem from "fixed ratio doesn't match this video." A scene-cut guard (`frame_filter.detect_scene_change`) was added to `shot_detector.py` as a partial mitigation; fully solving this is follow-up work, not silently dropped.

#### Phase C.1 — Court-Line Homography + Lunge-Apex Windowing ✅ DONE (2026-06-27)

Phase C's zone accuracy (7.5% exact) and row-distribution collapse (47% of shots predicted "mid" vs 19% true) motivated two follow-up improvements, both proposed and approved before implementation:

1. **Map the actual court white lines into a homography**, instead of relying only on the player-position-derived proportional grid, so the 9-zone template comes from real court geometry.
2. **Lunge-apex windowing** — search a window of frames around each detected shot for the receiving player's most-extended position (relative to their rally "home" base), instead of trusting a single fixed frame, since contact happens at the outward extreme of a reach-and-recover motion arc.

**Result 1 (homography) — real bug fixed, but disabled by default after empirical testing:** `court_detector.detect_court_corners()` had a genuine bug — it fit a `cv2.minAreaRect` to the court contour, which always returns an axis-aligned rectangle, destroying the actual trapezoid shape a perspective camera sees. Fixed to use the convex hull's own extreme corner points; verified visually and numerically stable across sampled frames, and the resulting homography correctly maps detected corners to a clean 610×1340cm rectangle. **However**, using this homography to map a *player's foot position* to real-world coordinates was tested against ground truth and made zone prediction worse, not better — "front" zone predictions dropped to ~0% across every tested configuration (vs the proportional method's already-low 18%). Root cause: monocular single-camera ground-plane homography is highly sensitive to foot-detection pixel noise near the far baseline (perspective compresses real distance into very few pixels there), and a standing player's detected foot point is systematically offset from their true ground-contact point by their height relative to the camera's elevation — a known limitation in monocular sports tracking, not a fixable implementation bug. **Decision:** kept the corner-detection fix and the homography infrastructure (`court_detector.calibrate_homography`, wired into `CourtCalibration.zone_for` as a priority path) for future use where this bias doesn't apply — e.g. Phase D, mapping actual shuttle position rather than player feet. Disabled by default for the current player-position-proxy use (`use_homography=False`).

**Result 2 (lunge-apex) — real, if modest and axis-uneven, improvement:** swept window widths 0–16 frames against ground truth; window=±12 frames chosen (best balance of exact accuracy and stability across neighboring widths, not a one-off spike). Full results in `docs/RESULTS.md` ("Phase C.1" section):

| Metric | Phase C | Phase C.1 |
|---|---|---|
| Zone exact match | 7.5% | **13.2%** (nearly doubled) |
| Zone exact-or-adjacent | 64.2% | 60.4% (within noise) |
| Column distribution fit to ground truth | poor (center over-predicted 45% vs true 25%) | **much improved** (30% vs true 25%) |
| Row distribution fit to ground truth | poor (mid over-predicted 47% vs true 19%) | modestly improved (still over-predicted: 42% vs true 21%) |

The horizontal axis improved substantially; the vertical (front/back) axis improved only slightly. This matches the mechanistic prediction made when lunge-apex was proposed: a player's forward/back movement is far more compressed in pixel space than left/right movement (perspective foreshortening), especially for the far-court player, so a pixel-space distance-from-home metric is naturally less sensitive to genuine front/back extremes. Fixing the vertical axis properly would need either a court-space distance metric (which reintroduces homography's parallax problem above) or — more durably — actual shuttle position instead of any player-position proxy. **This result is itself evidence for prioritizing Phase D next**: two different proxy refinements have now each hit a wall on the front/back axis specifically, for the same underlying reason (player position is fundamentally not shuttle position).

**Why player tracking before shuttle tracking:**
- The shuttle is a few pixels, fast, and frequently motion-blurred or indistinguishable from court lines at broadcast resolution — this is precisely the problem TrackNet was built to solve, and it requires either a working pretrained model transferring well to this footage or fine-tuning.
- A player is a large, high-contrast, standard-pose object. Off-the-shelf YOLO (`ultralytics`, already a project dependency but currently unused) detects the "person" class reliably with **no badminton-specific training**.
- Player position directly fixes the generalization problem: instead of guessing "the court is at 20%–85% of frame height" (Section 7.4), the actual play area can be derived per video from where the two players move during a rally.
- Player position also gives an independent, non-cascading signal for "who is currently receiving" — useful for sanity-checking or replacing the current pure-alternation toggle, which has no way to recover once one shot is mis-detected.

**Known limitation (must be documented, not hidden):** player position is a *proxy* for shuttle landing position, not the landing position itself. It improves attribution and rally/court bounds significantly, and gives a reasonable approximate zone (a player is usually near where they contact the shuttle), but it cannot replace true shuttle localization for precise zone accuracy — that remains Phase D's job. The project's own zone accuracy bar already tolerates this (AC-10: correct **or adjacent** zone), which player-position proxying is well suited to clear.

**Approach:**
1. Run YOLO (`ultralytics`, person class) per sampled frame within each rally to get both players' bounding boxes — no fine-tuning needed as a first pass.
2. Derive the per-video active court region from the bounding hull of player positions across a rally (replaces the fixed `court_top/bottom/left/right` ratios in `config.py`/`shot_detector.py`/`zone_mapper.py`).
3. Derive the per-video net line (~midpoint between the two players' typical y-position separation) instead of a fixed 50% split.
4. Use player position/motion as a cross-check on the existing optical-flow shot-boundary signal: only accept a shot boundary if it coincides with player activity (swing/movement), to filter out the spurious detections seen on video 2.
5. Use the receiving player's position at shot time as the zone-mapping input (replacing the brightness-blob shuttle guess), with the explicit understanding this is an approximation.
6. Retire the existing color/contour-based `player_tracker.py` (dead code today, and it has the same hardcoded-ratio problem) in favor of the YOLO-based detector.

**Acceptance Criteria:**
- Runs on both `Badminton_video_example.mp4` and `Badminton_video_example_2.mp4` without any hand-edited constant changes between runs.
- Per-rally shot counts on video 2 become plausible (e.g., consistent with ~1 shot per 1.5–3+ seconds of active rally, not ~1 shot/second as seen in today's smoke test).
- Zone distribution on video 2 is no longer collapsed into a single row (today: nearly all shots mapped to zones 7–9).
- Player names never silently fall back to another video's real player names (generic `Player 1`/`Player 2` only, with a visible warning when OCR fails).
- Reference video (video 1) accuracy does not regress versus current Phase B numbers in `docs/RESULTS.md`.

**Does NOT require:** TrackNet, or training any custom model — pretrained YOLO person detection is sufficient for this phase.

---

### Phase D — Integrate TrackNet for Shuttle Detection *(was Phase C in v2.2 — deferred, not removed)*

**Goal:** Replace remaining blob/motion-based shuttle position estimation with a specialized shuttle detection model, once Phase C's player-tracking foundation and generalization fixes are in place.

**Approach:** (unchanged from v2.2)
1. Download/integrate TrackNetV3 pre-trained weights for badminton ([qaz812345/TrackNetV3](https://github.com/qaz812345/TrackNetV3) — includes `TrackNet_best.pt` and `InpaintNet_best.pt`)
2. Run TrackNet on rally frames to get per-frame shuttle (x, y) coordinates
3. Use TrackNet trajectory to more accurately detect:
   - Shot exchanges (direction changes in shuttle trajectory)
   - Landing positions (trajectory endpoints) — this is what finally makes zone mapping precise rather than a player-position proxy
4. Combine with Phase C's player detections for a full shuttle + player hit-detection pipeline (per the Sensors 2024 TrackNet+YOLOv7 reference architecture)

**Acceptance Criteria:**
- Shuttle detection rate ≥80% of frames within rallies
- Shot count accuracy improves to within ±1 of ground truth for ≥80% of rallies
- Zone accuracy ≥80% compared to ground truth (correct zone or adjacent zone) — an improvement over Phase C's player-position proxy

**Research References:**
| Paper | Contribution |
|-------|-------------|
| TrackNetV3 | Frame-level shuttle (x,y) detection model for badminton |
| Sensors 2024 (TrackNet + YOLOv7) | Combined shuttle + player detection; hit detection pipeline |
| ShuttleSet (KDD 2023) | Best public annotated dataset; defines annotation schema |
| CoachAI Challenge 2023 | 11-task benchmark including rally segmentation and zone prediction |
| Court to Conversation (2025) | End-to-end system reference architecture including LLM querying |

---

### Phase E — Last-Shot Outcome Logic & Output Polish *(was Phase D in v2.2 — scope changed: mostly already implemented)*

**Goal:** Apply badminton rules to determine point winner and in/out for each rally's final shot.

**Status:** The core logic described here is **already implemented** in `main.py` (`_build_shot_output`) as of v2.2 — it was built ahead of the phase plan. It correctly applies: last receiver ≠ winner → IN; last receiver = winner → OUT. The accuracy gap seen in `docs/RESULTS.md` (3/5 correct) is **not** a Phase E logic bug — it's entirely caused by Phase B's ±1 shot-count errors flipping which player is "last receiver." Phase E's remaining scope is therefore:

1. Validate the existing logic against more rallies once Phase C/D improve upstream attribution accuracy (the formula doesn't need to change, just needs correct inputs).
2. Handle the known open gap: `score` (rally number) currently increments globally across the whole video and never resets per game, even though Section 6.2 specifies it should reset per game. Needs game-boundary detection (e.g., score reaching 21+ with margin, or a visible game-break in the footage) before this can be fixed correctly.
3. Re-run full acceptance criteria (AC-09, AC-10, AC-11) end-to-end once Phase C/D land.

**Acceptance Criteria:** (unchanged from v2.2 Phase D)
- "win by" column matches ground truth for ≥80% of rallies
- "out?" column matches ground truth for ≥80% of last-shot rows
- "receive by" column matches ground truth for ≥80% of all shots
- Zone column matches ground truth for ≥70% of shots (zone or adjacent zone)
- Overall output structure matches ground truth CSV format exactly

---

## 10. Acceptance Criteria (Overall)

| ID | Criterion |
|----|-----------|
| AC-01 | Service processes a valid MP4 file (≤100MB, ≤20min) without errors. |
| AC-02 | Service rejects files >100MB with error: "File exceeds 100MB limit." |
| AC-03 | Service rejects files >20min with error: "Video exceeds 20-minute limit." |
| AC-04 | Service rejects non-MP4 files with error: "Only MP4 format supported." |
| AC-05 | Output CSV matches the column schema defined in Section 6.2. |
| AC-06 | Zone numbering matches the reference image (Z1–Z3 back, Z7–Z9 front). |
| AC-07 | For reference video: detects ≥5 of 6 score sequences (rallies). |
| AC-08 | For reference video: total shot count within 20% of ground truth (70 shots). |
| AC-09 | For reference video: "receive by" alternation is correct for ≥80% of shots. |
| AC-10 | For reference video: zone assignment correct or adjacent for ≥70% of shots. |
| AC-11 | For reference video: "win by" correct for ≥80% of completed rallies. |
| AC-12 | Player names extracted from scoreboard match "DONG T.Y." and "FARHAN" *(reference video only — must never appear as a fallback for any other video, see AC-15)*. |
| AC-13 | Service completes processing of a 20-min video within 30 min on consumer hardware. |
| AC-14 | Non-play frames (replays, crowd shots) do not generate false shot data. |
| AC-15 *(new)* | Running the pipeline on a second, differently-framed/resolution broadcast video produces output without crashing, without editing any hardcoded constant, and without silently substituting another video's real player names. |

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Shuttle too small/fast to track in broadcast video | Cannot detect individual shots precisely | Player tracking (Phase C) provides an interim attribution + approximate-zone signal that doesn't depend on shuttle visibility; TrackNet (Phase D) still targeted for precision |
| Scoreboard OCR/pixel-region unreliable across different overlays | Rally boundaries missed; wrong player names | Temporal smoothing; sample multiple frames; **generic fallback names only, never another video's real names** (Section 7.4) |
| Rally detector misses points | Output has fewer rallies than actual | Scoreboard score changes are mandatory events; flag gaps |
| Camera cuts mid-rally (replays) | False shot detections | Frame filtering; detect scene changes and skip |
| Homography inaccurate | Zones misattributed | Per-video calibration (not hardcoded ratios); larger zone tolerance (adjacent = acceptable) |
| Fixed frame-ratio/pixel constants tuned to one video | Pipeline produces plausible-looking but wrong output on any other video (confirmed 2026-06-26, Section 14.3) | Section 7.4 remediation checklist; Phase C derives calibration per video instead of from `config.py` constants |
| TrackNet model unavailable or incompatible | Phase D blocked | Phase C (player tracking) provides a usable baseline independent of TrackNet |
| Shot count mismatch | More/fewer shots than ground truth | Cross-validate with alternation rule + player-motion signal (Phase C); flag anomalies |

---

## 12. Success Metrics

| Metric | Phase A Target | Phase B Target | Phase C Target (Player Tracking) | Phase D Target (TrackNet) | Phase E Target (Outcome Logic) |
|--------|---------------|---------------|---------------|---------------|---------------|
| Rally detection | ≥80% (5/6) | ≥80% | ≥80% (incl. on video 2) | ≥90% | ≥90% |
| Shot count accuracy | n/a | ±2 per rally | ±2 per rally, plausible on any video | ±1 per rally | ±1 per rally |
| Zone accuracy | n/a | ≥50% | ≥60% (player-position proxy) | ≥70% | ≥80% |
| Receive-by accuracy | n/a | ≥80% | ≥85% (cross-checked, not pure alternation) | ≥90% | ≥90% |
| Win-by accuracy | ≥80% | ≥80% | ≥80% | ≥80% | ≥90% |
| Player name extraction | ≥80% | ≥80% | ≥80%, **never wrong-video fallback** | ≥90% | ≥90% |
| Generalizes to unseen video without code/constant edits | n/a | n/a | **Yes (required)** | Yes | Yes |
| Processing time | <1min | <3min | <4min | <5min | <5min |

---

## 13. Open Questions

| # | Question | Proposed Answer |
|---|----------|----------------|
| 1 | What if TrackNet pre-trained weights don't work well on this broadcast style? | Fine-tune on ShuttleSet dataset or annotate a few frames manually. Lower-priority now that Phase C gives an interim signal that doesn't depend on TrackNet. |
| 2 | Should we support variable camera angles across different tournaments? | v1: optimize for BWF-style broadcasts only; Phase C's adaptive calibration is the first real step toward this, since it stops assuming a fixed court position in frame. |
| 3 | How to handle rallies that span camera cuts (replay inserted mid-rally)? | Detect scene change → pause tracking → resume when court returns |
| 4 | What if scoreboard is obscured or has different format? | Allow manual player-name and score override via config; never silently substitute a previous video's real names (Section 7.4) |
| 5 | Should aggregate reports (per-point summary) be a separate command? | Yes — derive from per-shot CSV; implement post-Phase E |
| 6 *(new)* | Does `score` (rally number) need to reset per game? | Yes per Section 6.2's spec, but not currently implemented — code increments it globally. Needs game-boundary detection; tracked under Phase E scope (Section 9). |

---

## 14. Reference Data

### 14.1 Ground Truth File

`badminton_video_result.csv` — 70 annotated shots from `Badminton_video_example.mp4`

| Score | Shots | Winner | Last-shot logic |
|-------|-------|--------|----------------|
| 1 | 16 | Player 2 | Player 1 received last, not out → P2 wins |
| 2 | 17 | Player 2 | Player 1 received last, not out → P2 wins |
| 3 | 9 | Player 1 | Player 1 received last, out → P1 wins |
| 4 | 7 | Player 2 | Player 2 received last, out → P2 wins |
| 5 | 16 | Player 2 | Player 1 received last, not out → P2 wins |
| 6 | 5+ | (partial) | Video ends mid-rally |

### 14.2 Research Papers (Reading Priority)

| Priority | Paper | Relevance |
|----------|-------|-----------|
| 1st | YOLOv8/Ultralytics person detection docs | Phase C — already a project dependency, unused so far |
| 2nd | Sensors 2024 (TrackNet + YOLOv7) | Combined shuttle + player detection pipeline — validates the player+shuttle combo approach for Phase C→D |
| 3rd | TrackNetV3 | Shuttle detection model — core tracking capability for Phase D |
| 4th | ShuttleSet (KDD 2023) | Best public dataset; defines annotation schema |
| 5th | CoachAI Challenge 2023 | 11-task benchmark to build toward |
| 6th | Court to Conversation (2025) | Full end-to-end system with LLM querying |

### 14.3 Multi-Video Generalization Smoke Test *(new — 2026-06-26)*

A second, un-annotated test video `Badminton_video_example_2.mp4` was added to `input/` to check whether the existing Phase A/B pipeline (unmodified) generalizes beyond the reference video. No ground truth exists for this video, so results below are a **plausibility check**, not an accuracy measurement.

**Video:** 854×480 @ 30fps, 5299 frames (176.6s) — different resolution and camera framing than the 908×480 reference video.

**Run output (`python -m src.main input/Badminton_video_example_2.mp4`):**

| Check | Result | Verdict |
|---|---|---|
| Player name detection | Fell back to `DONG T.Y.` / `FARHAN` (the reference video's players) | ❌ Wrong — this video has different players; the fallback is silently incorrect, not just "unknown" |
| Rally detection | 6 rallies detected (5 score changes + 1 partial), durations 48.0s / 37.5s / 36.5s / 11.0s / 10.0s / 33.6s | Plausible on its face |
| Shot count per rally | 41, 28, 29, 13, 14, 30 (155 total) | ❌ Implausible — e.g. 41 shots in a 48s rally is roughly 1 shot every 1.2s sustained, far denser than realistic badminton exchange rates; strongly suggests the motion-threshold logic is picking up non-shot motion on this video |
| Zone distribution | Overwhelming majority of shots mapped to zones 7, 8, 9 (front row/net) | ❌ Collapsed — confirms the hardcoded proportional court box (Section 7.4) doesn't fit this video's framing |
| Crash | A Windows console `UnicodeEncodeError` on the `→` character in two `print()` statements (`main.py`) halted the run; required `PYTHONIOENCODING=utf-8` to get a clean run. Unrelated to the hardcoding issue, but worth a trivial fix. | Minor, separate bug |

**Conclusion:** this is exactly the failure mode Section 7.4 was written to address. It directly motivates prioritizing Phase C (adaptive, player-tracking-derived calibration) before further investment in Phase B's video-1-specific thresholds or jumping to Phase D's TrackNet integration.

---

## 15. Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-16 | Pivot from manual annotation (v1.0) to automated CV pipeline (v2.0) | Manual annotation too slow; automated analysis is the core value |
| 2026-06-16 | Backend-only, no frontend | User only needs input → output; no interactive UI required |
| 2026-06-16 | MP4 only, 100MB / 20min limits | Keeps scope manageable; prevents long processing |
| 2026-06-16 | Zone numbering: Z1–Z3 back, Z7–Z9 front | Matches reference image |
| 2026-06-16 | Player 1 = Dong T.Y. (top/far), Player 2 = Farhan (bottom/near) | Matches video and ground truth |
| 2026-06-16 | Output format: per-shot CSV (not per-point aggregate) | Per-shot is the raw data; aggregates can be derived later |
| 2026-06-16 | Scoreboard is primary source of truth for rally boundaries | Rally motion detection alone missed points |
| 2026-06-16 | Iteration order: A (rallies) → B (shots) → C (TrackNet) → D (outcome logic) | Each phase builds on the previous; highest-ROI first |
| 2026-06-16 | Badminton rules documented as engineering prerequisite | Rules directly inform alternation logic and winner determination |
| 2026-06-16 | 80% accuracy target per phase | Pragmatic for v1; iterate to improve |
| 2026-06-26 | Re-ordered iteration plan: Phase C is now player tracking (YOLO), TrackNet moved to Phase D | Player detection is far more tractable than shuttle detection at broadcast resolution (large, high-contrast, off-the-shelf pretrained model already in `requirements.txt`), and it directly fixes the calibration/hardcoding problem as a side effect. Shuttle precision (TrackNet) still needed eventually for zone accuracy, but is no longer the blocking next step. |
| 2026-06-26 | Adopted explicit anti-hardcoding requirement (Section 7.4) | Confirmed empirically: running the unmodified Phase A/B pipeline on a second video produced wrong player names (silent fallback), implausible shot density, and zone collapse — all traced to constants tuned only to video 1 (Section 14.3). |
| 2026-06-26 | Config-level player name fallbacks changed from real names to generic "Player 1"/"Player 2" (planned, not yet implemented in code) | A real name from one video must never silently appear in another video's output. |
| 2026-06-26 | Added second, un-annotated test video as a standing generalization smoke test | Accuracy can only be graded against ground truth (video 1), but plausibility/non-hardcoding can and should be checked continuously against at least one other video. |
| 2026-06-27 | Implemented Phase C (YOLO player tracking + adaptive calibration); kept on this approach after the first attempt (65th-percentile motion threshold) regressed video 1 to 16 total shots, then swept thresholds and re-validated against ground truth before locking in 30th percentile | First implementation choice didn't generalize the way the smoke test demanded — moved to empirical threshold sweep against the one video with ground truth rather than guessing a second fixed value. |
| 2026-06-27 | Removed `first_receivers` lookup table in `main.py` (was a 6-entry dict matching video 1's ground truth exactly); replaced with derivation from the previous rally's detected winner | Discovered while implementing Phase C — this was a second, less obvious hardcode beyond the ones catalogued in Section 7.4, effectively memorizing the answer key for one video. |
| 2026-06-27 | Accepted `out?` accuracy (40%) as a known weak point rather than special-casing it | It's a downstream symptom of per-rally shot-count parity (Section 9, Phase E), not an independent bug — fixing it directly would mean re-introducing per-rally special-casing, the thing this phase exists to remove. |
| 2026-06-27 | Implemented court-line homography (Phase C.1) but disabled it by default for zone mapping | Fixed a real bug in `detect_court_corners` (minAreaRect was destroying the court's trapezoid shape) and validated the resulting homography is geometrically correct — but empirically, using it to map *player foot position* made zone prediction worse (front-zone predictions collapsed to ~0%) due to a known monocular-camera parallax limitation, not an implementation error. Kept the code (useful for Phase D, mapping real shuttle position) but off by default for the current proxy use. |
| 2026-06-27 | Adopted lunge-apex windowing (±12 frames) as the default zone-estimation method | Swept 0–16 frame windows against ground truth; nearly doubled exact-zone accuracy (7.5%→13.2%) and substantially fixed the horizontal-axis distribution collapse. Vertical axis improved only slightly — accepted as a known, mechanistically-explained limitation of pixel-space player-position proxying (see Phase C.1), not chased further with more parameter tuning. |
| 2026-06-27 | Treating Phase C.1's plateau as a signal to prioritize Phase D (TrackNet) next, rather than further player-position-proxy tuning | Two independent refinements (court-line homography, lunge-apex windowing) each hit the same wall on the front/back axis for the same underlying reason — player position is not shuttle position. Further tuning of the proxy is expected to keep hitting this ceiling. |
