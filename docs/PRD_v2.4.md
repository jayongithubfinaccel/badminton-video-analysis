# Badminton Video Analysis Service — PRD v2.4

> **Version:** 2.4 — Visual QA / Debug Tooling
> **Status:** Active
> **Author:** Jayson Fetra
> **Date:** 09 July 2026
> **Platform:** Backend Python service (CLI)
> **Supersedes:** PRD v2.3

---

## 0. What Changed in v2.4

This revision does **not** change the product goals or scored output pipeline (Sections 1–8 are unchanged from v2.3). It adds one new, diagnostic-only phase:

1. **Add Phase F: Visual QA / debug tooling.** Formalizes the ad hoc visual-audit approach that found the most recent shipped bug (the back-row/mid-row zone-collapse fix, 2026-07-03/05 — see `DEPLOYMENT_LOG.md`) into reusable, tested tooling instead of a one-off script rewritten for every new investigation: (a) random-sampled annotated frame screenshots, and (b) a full annotated debug video. Both overlay four signals: the 9-zone court grid, player foot position, racket position (a new, best-effort detection target), and shuttlecock position. Off by default; explicitly diagnostic-only; **not** wired into any scoring logic (shot detection, zone mapping, outcome logic).

No development has started on this phase yet — this document is the plan.

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
- Generalize across different broadcast videos without per-video code or constant changes
- **Provide reusable visual QA tooling so tracking/calibration errors can be diagnosed from real frames instead of ad hoc scripts** (new in v2.4)

### 3.2 Non-Goals (v1)

- No frontend / UI / web interface
- No real-time / streaming analysis (batch processing only)
- No doubles match support
- No shot-type classification (e.g., smash vs drop) — only landing zone
- No cloud deployment — local execution only
- No video editing or highlight generation
- No per-point aggregate output (can be derived from per-shot data later)
- No interactive review UI for the new debug tooling — output is files (PNG/MP4) opened manually (new in v2.4)
- No racket-specific model training, and racket detection is not wired into any scoring logic (new in v2.4 — see Phase F)

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
| 7. Player Tracking | Detect player bounding boxes frame-by-frame within rallies | Derive court bounds + shot attribution |
| 8. Shuttle Tracking | Track shuttle position frame-by-frame within rallies | Detect individual shot exchanges |
| 9. Shot Detection | Identify each individual hit/exchange | One shot = shuttle going from one side to the other |
| 10. Player Attribution | Determine who received each shot | Confirmed by player position, not just alternation |
| 11. Zone Mapping | Map shuttle landing coordinates to zones 1–9 | Fill "zone (receive by)" column |
| 12. Last-Shot Logic | Apply badminton rules to determine winner/out | Fill last_receive, out, win_by columns |
| 13. Output Generation | Write per-shot CSV | Deliver final results |
| 14. Visual Debug Overlay *(new, v2.4)* | Render court grid + player foot + racket + shuttle onto sampled frames / a debug video | Diagnose tracking/calibration errors from real frames (Phase F) |

### 7.3 Folder Structure

```
badminton-video-analysis/
├── input/                  # Place video files here
├── output/                 # Analysis results written here
│   ├── debug_frames/       # (new, v2.4) Sampled annotated PNGs, one subfolder per video
│   └── debug_video/        # (new, v2.4) Full annotated debug MP4s
├── src/
│   ├── main.py            # CLI entry point & pipeline orchestrator
│   ├── config.py          # Configuration constants (per-video calibration must NOT live here as fixed values — see 7.4)
│   ├── pipeline/
│   │   ├── validator.py       # Input validation
│   │   ├── court_detector.py  # Court detection & homography
│   │   ├── frame_filter.py    # Non-play frame detection
│   │   ├── scoreboard_ocr.py  # Player names + score extraction
│   │   ├── rally_segmenter.py # Rally boundary detection
│   │   ├── player_detector.py # Player position & attribution (YOLO)
│   │   ├── shuttle_tracker.py # Shuttle position tracking (TrackNetV3)
│   │   ├── shot_detector.py   # Individual shot/exchange detection
│   │   ├── court_calibration.py # Coordinate → zone mapping
│   │   ├── debug_overlay.py   # (new, v2.4) Draws court grid/foot/racket/shuttle overlays — one shared function for both debug deliverables
│   │   └── frame_sampler.py   # (new, v2.4) Seeded random sampling of frame indices within rally windows
│   ├── models/                # ML model weights (YOLO, TrackNet, etc.)
│   └── utils/
│       └── export.py          # CSV output generation
├── tests/
│   └── test_against_ground_truth.py  # Validation against reference CSV
├── data/
│   ├── ground_truth/          # Reference CSVs for validation
│   └── models/                # Downloaded model weights
├── docs/
│   └── PRD_v2.4.md
├── requirements.txt
└── pyproject.toml
```

### 7.4 Generalization & Anti-Hardcoding Requirements

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

> **v2.4 note:** the new racket-detection overlay (Phase F) is explicitly exempted from being treated as a load-bearing signal at all — see Phase F's non-goals. It is diagnostic-only, so it is not subject to this section's accuracy bar, only to "doesn't crash / doesn't mislead the viewer."

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

debug:                                 # new in v2.4 — see Phase F
  frames_output_folder: "./output/debug_frames"
  video_output_folder: "./output/debug_video"
  default_sample_count: 30             # frames sampled when --debug-frames is passed with no explicit N
  racket_coco_class_id: 38             # "tennis racket" — best-effort proxy, unvalidated on badminton rackets
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

**Status:** Implemented (`shot_detector.py`) via optical-flow direction-reversal + alternation. 70/70 total shot count on reference video, but with ±1 per-rally errors that cascade into wrong attribution on 3 of the rallies' last shots (see `docs/RESULTS.md`). Confirmed to **not generalize** to a second video (implausible shot density, zone collapse — Section 14.3). This is the motivation for Phase C below.

---

### Phase C — Player Detection & Adaptive Calibration ✅ DONE (2026-06-27)

**Goal:** Use player position, not shuttle position, to (1) remove the hardcoded frame-ratio assumptions flagged in Section 7.4, and (2) make shot attribution robust to single-frame errors instead of a blind toggle that cascades.

**Status:** Implemented (`player_detector.py`, `court_calibration.py`, updated `shot_detector.py`/`main.py`). Full results in `docs/RESULTS.md` ("Phase C" section). Summary:
- Video 1 (ground truth): 21.4% total shot-count error, 27.5% average per-rally count error (under the 30% bar), 88.7% `receive by` accuracy, **100% `win by` accuracy** (up from 60% in Phase B), 64.2% zone-correct-or-adjacent. Weak point: `out?` accuracy (40%), tied to per-rally shot-count parity, not a new bug.
- Video 2 (no ground truth, generalization check): same code/constants as video 1, produced plausible shot density and a zone distribution spread across all 9 zones. Player names correctly fell back to generic placeholders with a visible warning instead of silently reusing video 1's real names.
- Removed an additional hidden hardcode found during implementation: the `first_receivers` lookup table in `main.py` was a 6-entry dict reverse-fit to video 1's ground truth. Replaced with a derivation from the previous rally's detected winner (rule: rally winner serves next).
- New known limitation: video 2 contains genuine multi-camera-angle production cuts *within* a single rally. A scene-cut guard (`frame_filter.detect_scene_change`) was added to `shot_detector.py` as a partial mitigation.

#### Phase C.1 — Court-Line Homography + Lunge-Apex Windowing ✅ DONE (2026-06-27)

Two follow-up improvements: mapping court white lines into a homography, and lunge-apex windowing (searching a window of frames around each shot for the receiving player's most-extended position).

**Result 1 (homography) — real bug fixed, but disabled by default after empirical testing:** `court_detector.detect_court_corners()` had a genuine bug (`cv2.minAreaRect` destroyed the court's trapezoid shape); fixed, verified geometrically correct, but using it for zone mapping made predictions worse due to monocular parallax bias. Kept the infrastructure for future use (e.g. Phase D shuttle mapping), disabled by default for player-position proxying.

**Result 2 (lunge-apex) — real, if modest and axis-uneven, improvement:** window=±12 frames chosen via sweep. Zone exact match 7.5%→13.2%, column-axis distribution much improved, row (front/back) axis only modestly improved — a mechanistic ceiling from perspective foreshortening on the vertical axis, motivating Phase D next.

**Acceptance Criteria:** met — see `docs/RESULTS.md` "Phase C.1".

---

### Phase D — Integrate TrackNet for Shuttle Detection ✅ DONE (2026-06-29)

**Goal:** Replace the player-position proxy with real shuttle position.

**What was built:** Integrated TrackNetV3 (pretrained, `TrackNetV3_src/`) via `shuttle_tracker.py`, wired as the primary zone-position source with a fallback to the Phase C.1 lunge-apex proxy if TrackNetV3 isn't set up. 77.3% shuttle visibility rate on video 1.

**Key finding:** raw shot-frame shuttle position is worse than the player proxy — the shuttle is still airborne at the optical-flow-detected shot frame. Fix: search for the shuttle's local lowest point strictly between the previous shot and this one.

**Result (video 1):** zone exact-or-adjacent unchanged at 60.4% vs Phase C.1 (criterion not met), but column-axis distribution divergence improved substantially (0.19→0.04). Row axis improved only slightly — this became the motivation for the Phase D follow-up fix below.

**Video 2 generalization check:** a path-separator bug in `ensure_ball_predictions()` (Unix-style `split('/')` silently breaking on Windows paths) was found and fixed; the recovered real shuttle data then exposed a second, genuine finding — `zone_for()`'s proportional-grid clamping collapses real shuttle landing points into the back row when they fall outside the player-foot-derived calibration bounds. This is what the Phase D follow-up (below) fixes.

#### Phase D follow-up — Shuttle-Derived Row Recalibration ✅ DONE (2026-07-03/05)

**Goal:** Fix the row-axis (front/back) zone collapse exposed by Phase D's video-2 finding.

**Root cause (found via a manual visual audit — the direct motivation for Phase F below):** overlaying the calibrated grid, YOLO player boxes, and TrackNetV3 shuttle points on real frames showed the row-axis bounds (`top`/`bottom`/`net_y`), derived from player-**foot** positions, placed the back-row/mid-row boundary only ~3px from the real baseline on video 1 — so nearly the entire "back row" zone band fell off the actual court surface, and real back-court shots were systematically bucketed as "mid."

**Fix:** `recalibrate_from_shuttle_positions()` (`court_calibration.py`) re-derives `top`/`bottom`/`net_y` from the 5th/95th percentile of *real* TrackNetV3 shuttle landing Y-values once shots are known, leaving the already-accurate column axis (`left`/`right`) untouched. Parameters swept against video 1's ground truth.

**Result:** video 1 zone exact match 13.2%→17.0%, zone exact-or-adjacent 60.4%→64.2%, row-distribution divergence 0.528→0.340, column axis unchanged (0.038, confirming the fix is row-only). Video 2 (plausibility): front-row share 2.4%→37.8%.

**Honest read:** not a complete fix — 64.2% remains well under the Phase E 80% target. Full detail: `DEPLOYMENT_LOG.md` (2026-07-03 entry) and `docs/RESULTS.md`.

**Research References:**
| Paper | Contribution |
|-------|-------------|
| TrackNetV3 | Frame-level shuttle (x,y) detection model for badminton |
| Sensors 2024 (TrackNet + YOLOv7) | Combined shuttle + player detection; hit detection pipeline |
| ShuttleSet (KDD 2023) | Best public annotated dataset; defines annotation schema |
| CoachAI Challenge 2023 | 11-task benchmark including rally segmentation and zone prediction |
| Court to Conversation (2025) | End-to-end system reference architecture including LLM querying |

---

### Phase E — Last-Shot Outcome Logic & Output Polish

**Goal:** Apply badminton rules to determine point winner and in/out for each rally's final shot.

**Status:** The core logic described here is **already implemented** in `main.py` (`_build_shot_output`). It correctly applies: last receiver ≠ winner → IN; last receiver = winner → OUT. Remaining scope:

1. Validate the existing logic against more rallies once Phase C/D/D-followup improve upstream attribution accuracy.
2. Handle the known open gap: `score` (rally number) currently increments globally across the whole video and never resets per game. Needs game-boundary detection.
3. Re-run full acceptance criteria (AC-09, AC-10, AC-11) end-to-end.

**Acceptance Criteria:**
- "win by" column matches ground truth for ≥80% of rallies
- "out?" column matches ground truth for ≥80% of last-shot rows
- "receive by" column matches ground truth for ≥80% of all shots
- Zone column matches ground truth for ≥70% of shots (zone or adjacent zone)
- Overall output structure matches ground truth CSV format exactly

---

### Phase F — Visual QA / Debug Tooling (Frame Sampling + Annotated Overlay Video) *(new in v2.4)*

**Goal:** Give engineering a repeatable, tested way to see what each pipeline stage is actually detecting on real frames — court grid, player foot position, racket position, and shuttlecock position — instead of re-writing a one-off inspection script every time a new accuracy problem needs debugging.

**Motivation:** The Phase D follow-up fix above (2026-07-03/05) was found by manually overlaying the calibrated grid, YOLO player boxes, and TrackNetV3 shuttle points on real frames using a throwaway script — not committed, not reusable, not tested. Zone accuracy (64.2% exact-or-adjacent as of that fix) remains well below the Phase E target (80%), and every phase to date (C, C.1, D) was diagnosed by some form of ad hoc visual inspection of exactly these four signals. This phase formalizes that inspection workflow as first-class, reusable, tested tooling rather than a scratch script rebuilt by hand for each investigation.

**Scope (exactly what was requested, nothing broader):**

1. **Court grid** — the 9-zone grid derived from the active `CourtCalibration` (both the player-foot-derived pass and, when it ran, the Phase D-followup shuttle-recalibrated pass).
2. **Player foot position** — from the existing YOLO person-detection path (`player_detector.py`); already computed, no new inference needed.
3. **Racket position** *(new detection target)* — best-effort, using YOLOv8's pretrained COCO class 38 (`"tennis racket"`) alongside the existing person-class query. No badminton-specific racket model or training data exists; treated the same way other proxies in this project are treated (Section 7.4) — an unvalidated approximation, not a load-bearing signal.
4. **Shuttlecock position** — from the already-integrated TrackNetV3 output (`shuttle_tracker.py`), when available; draws no marker (never a fabricated point) on frames where TrackNetV3 reports no detection, consistent with its documented 77.3% visibility rate (Phase D).

**Deliverables:**

| Deliverable | Description | Output location |
|---|---|---|
| A. Sampled frame screenshots | Randomly sample N frames (default from config, e.g. 30) from within detected rally windows, draw all 4 overlays, save as PNG | `output/debug_frames/<video_name>/frame_<frame_number>.png` |
| B. Annotated debug video | Re-encode the analyzed footage (or a configurable subset of rallies) with the same overlays burned into every frame | `output/debug_video/<video_name>_annotated.mp4` |

**Technical approach:**
- New module `src/pipeline/debug_overlay.py` — a single pure function, `draw_overlays(frame, calibration, player_boxes, racket_boxes, shuttle_point) -> frame`, reused by both deliverables so overlay-drawing logic exists in exactly one place rather than being duplicated between the screenshot tool and the video renderer.
- New module `src/pipeline/frame_sampler.py` — seeded `random.sample` over frame indices drawn from the already-computed rally windows (reuses `Rally` objects from `rally_segmenter.py`; does not re-scan the whole video).
- Racket detection extends the existing YOLO call site in `player_detector.py` to also request COCO class 38, associating each detected racket box with the nearest player box by proximity (same top-2-by-confidence pattern already used for person detection).
- Video rendering reuses the `fps`/`frame_width`/`frame_height` already read once in `main.py`'s `_open_video()`; written via `cv2.VideoWriter`.
- New CLI flags on the existing `analyze` entry point: `--debug-frames [N]` and `--debug-video`, **both off by default** — this is diagnostic tooling with real runtime cost (an extra YOLO class query per sampled/rendered frame, plus full video re-encoding for deliverable B), not something that should silently slow down every normal run.

**Non-goals for this phase:**
- No racket-specific model training — pretrained COCO "tennis racket" only, explicitly flagged as unvalidated on badminton rackets.
- Racket detection is **not** wired into any scoring logic (shot detection, zone mapping, outcome logic) — overlay/diagnostic-only, to avoid introducing a new, unvalidated signal into the scored pipeline before it's proven useful. Promoting it to a real signal (e.g. a contact-point detector) would be a separate, future phase with its own validation against ground truth.
- No interactive review UI — output is PNG/MP4 files opened manually, consistent with this project's no-frontend scope (Section 3.2).

**Acceptance Criteria:**
- `analyze --debug-frames 20` on either test video produces 20 PNG files, each showing the court grid and at least one player foot marker; a shuttle marker is present whenever TrackNetV3 has data for that frame.
- `analyze --debug-video` produces a playable MP4 spanning the requested rallies with overlays visible on every frame, at the source video's native fps.
- `draw_overlays()` has unit test coverage against fixed, synthetic calibration/box inputs (verifying pixel-correct grid lines and marker placement), not just "runs without crashing."
- Both flags are no-ops (zero added runtime, zero added inference calls) when omitted from the command line.
- Documented in `ARCHITECTURE.md` as diagnostic tooling, explicitly separate from the scored per-shot output pipeline (Section 6).

**Does NOT require:** a new/fine-tuned racket model, a review UI, or any change to the scored CSV output pipeline.

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
| AC-15 | Running the pipeline on a second, differently-framed/resolution broadcast video produces output without crashing, without editing any hardcoded constant, and without silently substituting another video's real player names. |
| AC-16 *(new, v2.4)* | `--debug-frames`/`--debug-video` flags produce overlay screenshots/video showing court grid, player foot, racket (best-effort), and shuttle position (when available); both flags are no-ops (no runtime/inference cost) when omitted. |

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Shuttle too small/fast to track in broadcast video | Cannot detect individual shots precisely | Player tracking (Phase C) provides an interim attribution + approximate-zone signal that doesn't depend on shuttle visibility; TrackNet (Phase D) targeted for precision |
| Scoreboard OCR/pixel-region unreliable across different overlays | Rally boundaries missed; wrong player names | Temporal smoothing; sample multiple frames; generic fallback names only, never another video's real names (Section 7.4) |
| Rally detector misses points | Output has fewer rallies than actual | Scoreboard score changes are mandatory events; flag gaps |
| Camera cuts mid-rally (replays) | False shot detections | Frame filtering; detect scene changes and skip |
| Homography inaccurate | Zones misattributed | Per-video calibration (not hardcoded ratios); larger zone tolerance (adjacent = acceptable) |
| Fixed frame-ratio/pixel constants tuned to one video | Pipeline produces plausible-looking but wrong output on any other video (confirmed 2026-06-26, Section 14.3) | Section 7.4 remediation checklist; Phase C derives calibration per video instead of from `config.py` constants |
| TrackNet model unavailable or incompatible | Phase D blocked | Phase C (player tracking) provides a usable baseline independent of TrackNet |
| Shot count mismatch | More/fewer shots than ground truth | Cross-validate with alternation rule + player-motion signal (Phase C); flag anomalies |
| Racket detection (Phase F) misleads a viewer into treating it as ground truth | A reader of the debug video mistakes an unvalidated best-effort overlay for a validated signal | Explicitly label as diagnostic/unvalidated in `ARCHITECTURE.md` and never consume it in scoring logic (Phase F non-goals) |
| Debug tooling (Phase F) silently adds runtime cost to normal runs | Slower default pipeline, contradicting Section 7's processing-time targets | Both flags off by default; AC-16 requires verifying zero added cost when omitted |

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

**Current measured state (video 1, n=53, as of the Phase D follow-up fix, 2026-07-05):** zone exact match 17.0%, zone exact-or-adjacent 64.2% — still below the Phase E 80% target. This gap is the practical motivation for Phase F: further row/column-axis tuning needs a fast way to *see* where predictions diverge from real shuttle/court/player positions on actual frames.

> **v2.4 note:** Phase F (visual QA / debug tooling) is diagnostic infrastructure, not a detection-accuracy phase, and intentionally has no column in the table above — see Section 9, Phase F for its own, separately-scoped acceptance criteria.

---

## 13. Open Questions

| # | Question | Proposed Answer |
|---|----------|----------------|
| 1 | What if TrackNet pre-trained weights don't work well on this broadcast style? | Fine-tune on ShuttleSet dataset or annotate a few frames manually. Lower-priority now that Phase C gives an interim signal that doesn't depend on TrackNet. |
| 2 | Should we support variable camera angles across different tournaments? | v1: optimize for BWF-style broadcasts only; Phase C's adaptive calibration is the first real step toward this, since it stops assuming a fixed court position in frame. |
| 3 | How to handle rallies that span camera cuts (replay inserted mid-rally)? | Detect scene change → pause tracking → resume when court returns |
| 4 | What if scoreboard is obscured or has different format? | Allow manual player-name and score override via config; never silently substitute a previous video's real names (Section 7.4) |
| 5 | Should aggregate reports (per-point summary) be a separate command? | Yes — derive from per-shot CSV; implement post-Phase E |
| 6 | Does `score` (rally number) need to reset per game? | Yes per Section 6.2's spec, but not currently implemented — code increments it globally. Needs game-boundary detection; tracked under Phase E scope (Section 9). |
| 7 *(new)* | Should racket detection ever be promoted from diagnostic overlay to a real scoring signal (e.g. contact-point/shot-timing)? | Not yet — no accuracy validation exists for pretrained COCO "tennis racket" on badminton rackets at broadcast resolution. Revisit only after Phase F ships and someone has actually looked at how often it fires correctly on sampled frames. |

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
| 1st | YOLOv8/Ultralytics person detection docs | Phase C, and now Phase F's racket-class query |
| 2nd | Sensors 2024 (TrackNet + YOLOv7) | Combined shuttle + player detection pipeline — validates the player+shuttle combo approach for Phase C→D |
| 3rd | TrackNetV3 | Shuttle detection model — core tracking capability for Phase D |
| 4th | ShuttleSet (KDD 2023) | Best public dataset; defines annotation schema |
| 5th | CoachAI Challenge 2023 | 11-task benchmark to build toward |
| 6th | Court to Conversation (2025) | Full end-to-end system with LLM querying |

### 14.3 Multi-Video Generalization Smoke Test

A second, un-annotated test video `Badminton_video_example_2.mp4` was added to `input/` to check whether the existing Phase A/B pipeline (unmodified) generalizes beyond the reference video. No ground truth exists for this video, so results below are a **plausibility check**, not an accuracy measurement.

**Video:** 854×480 @ 30fps, 5299 frames (176.6s) — different resolution and camera framing than the 908×480 reference video.

**Run output (`python -m src.main input/Badminton_video_example_2.mp4`):**

| Check | Result | Verdict |
|---|---|---|
| Player name detection | Fell back to `DONG T.Y.` / `FARHAN` (the reference video's players) | ❌ Wrong — this video has different players; the fallback is silently incorrect, not just "unknown" |
| Rally detection | 6 rallies detected (5 score changes + 1 partial), durations 48.0s / 37.5s / 36.5s / 11.0s / 10.0s / 33.6s | Plausible on its face |
| Shot count per rally | 41, 28, 29, 13, 14, 30 (155 total) | ❌ Implausible — far denser than realistic badminton exchange rates |
| Zone distribution | Overwhelming majority of shots mapped to zones 7, 8, 9 (front row/net) | ❌ Collapsed — confirms the hardcoded proportional court box (Section 7.4) doesn't fit this video's framing |
| Crash | A Windows console `UnicodeEncodeError` on the `→` character halted the run; required `PYTHONIOENCODING=utf-8` | Minor, separate bug |

**Conclusion:** this is exactly the failure mode Section 7.4 was written to address; it motivated Phase C.

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
| 2026-06-26 | Re-ordered iteration plan: Phase C is now player tracking (YOLO), TrackNet moved to Phase D | Player detection is far more tractable than shuttle detection at broadcast resolution, and it directly fixes the calibration/hardcoding problem as a side effect. |
| 2026-06-26 | Adopted explicit anti-hardcoding requirement (Section 7.4) | Confirmed empirically: running the unmodified Phase A/B pipeline on a second video produced wrong player names, implausible shot density, and zone collapse — all traced to constants tuned only to video 1 (Section 14.3). |
| 2026-06-26 | Config-level player name fallbacks changed from real names to generic "Player 1"/"Player 2" | A real name from one video must never silently appear in another video's output. |
| 2026-06-26 | Added second, un-annotated test video as a standing generalization smoke test | Accuracy can only be graded against ground truth (video 1), but plausibility/non-hardcoding can and should be checked continuously against at least one other video. |
| 2026-06-27 | Implemented Phase C (YOLO player tracking + adaptive calibration) | First implementation choice didn't generalize the way the smoke test demanded — moved to empirical threshold sweep against the one video with ground truth rather than guessing a second fixed value. |
| 2026-06-27 | Removed `first_receivers` lookup table in `main.py` | This was a second, less obvious hardcode — effectively memorizing the answer key for one video. |
| 2026-06-27 | Accepted `out?` accuracy (40%) as a known weak point rather than special-casing it | It's a downstream symptom of per-rally shot-count parity, not an independent bug. |
| 2026-06-27 | Implemented court-line homography (Phase C.1) but disabled it by default for zone mapping | Fixed a real bug in `detect_court_corners`, but empirically using it for player-foot mapping made zone prediction worse due to monocular parallax. Kept the code for future use (Phase D shuttle mapping). |
| 2026-06-27 | Adopted lunge-apex windowing (±12 frames) as the default zone-estimation method | Nearly doubled exact-zone accuracy; vertical axis improved only slightly — accepted as a known, mechanistically-explained limitation. |
| 2026-06-27 | Treating Phase C.1's plateau as a signal to prioritize Phase D (TrackNet) next | Two independent refinements each hit the same wall on the front/back axis for the same underlying reason — player position is not shuttle position. |
| 2026-06-29 | Rejected raw "shuttle position at the detected shot frame" as the Phase D zone signal; replaced with a landing-point search between consecutive shots | The shuttle is still airborne (mid-flight height, not court depth) at the optical-flow-detected shot frame. |
| 2026-06-29 | Kept `shuttle_tracker.py` falling back to Phase C.1's lunge-apex proxy when TrackNetV3 isn't set up | Anti-hardcoding requirement (Section 7.4) extends to optional heavy dependencies: the pipeline must keep producing output, just less precisely, if the external model isn't installed. |
| 2026-06-29 | Did not claim Phase D met its ≥80% zone exact-or-adjacent acceptance criterion | Adjacent-match stayed at 60.4%, identical to Phase C.1 at n=53 — a real improvement in error *distribution* is not the same claim as meeting the accuracy bar. |
| 2026-06-30 | Corrected an initial wrong diagnosis: video 2's TrackNetV3 "failure" was not memory exhaustion — it was a path-separator bug in `ensure_ball_predictions()` | The fallback firing "correctly" doesn't mean the assumed cause was correct — verify the actual failure before writing it down. |
| 2026-06-30 | Found (via video 2's real shuttle data, after the path-bug fix) that `zone_for()`'s proportional-grid clamping can collapse real shuttle landing points into the back row | A player-position proxy can never expose this gap because the proxy's own positions are what the calibration was built from. |
| 2026-07-03/05 | Implemented shuttle-derived row recalibration (`recalibrate_from_shuttle_positions()`), fixing the back-row/mid-row collapse | Diagnosed via a manual visual audit overlaying the grid, YOLO boxes, and TrackNetV3 points on real frames — a one-off script, not committed tooling. This is the direct trigger for Phase F (v2.4). |
| 2026-07-09 | Added Phase F (visual QA / debug tooling): random-sampled annotated frame screenshots + a full annotated debug video, overlaying court grid, player foot, racket (new, best-effort), and shuttle position | The most recent shipped fix was diagnosed via a one-off, uncommitted visual-audit script overlaying exactly these signals. Formalizing it as tested, reusable tooling avoids re-writing the same inspection script for every future accuracy investigation, and gives a faster feedback loop for closing the Phase E zone-accuracy gap (currently 64.2% vs 80% target). |
| 2026-07-09 | Scoped racket detection as overlay/diagnostic-only, not wired into any scoring logic | No badminton-specific racket model exists; pretrained COCO "tennis racket" class accuracy on badminton racket shapes is unvalidated. Promoting it to a real signal (e.g. contact-point detection) is future work with its own validation, consistent with how this project treats other unvalidated proxies (Section 7.4). |
| 2026-07-09 | Made both debug flags (`--debug-frames`, `--debug-video`) off by default rather than always-on | This is diagnostic tooling with real runtime cost (extra YOLO class query, full video re-encoding) — it must not silently slow down or change the output of a normal scored run. |
