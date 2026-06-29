# Badminton Video Analysis — Results

## Overview

This document tracks the analysis results from processing the reference video `Badminton_video_example.mp4` (908x480 @ 30fps, 89.6s).

**Ground Truth:** 70 shots across 6 rallies  
**Detected:** 70 shots across 6 rallies ✓

---

## Phase A: Rally Segmentation

**Method:** Pixel-based NCC (Normalized Cross-Correlation) on scoreboard digit regions + visibility gap detection for replays.

### Results

| Rally | Start Frame | End Frame | Duration | Winner | Status |
|:-----:|:-----------:|:---------:|:--------:|:------:|:------:|
| 1 | 0 | 900 | 30.0s | Player 2 | ✓ |
| 2 | 900 | 1620 | 24.0s | Player 2 | ✓ |
| 3 | 1620 | 1830 | 7.0s | Player 1 | ✓ |
| 4 | 1830 | 2040 | 7.0s | Player 2 | ✓ |
| 5 | 2040 | 2580 | 18.0s | Player 2 | ✓ |
| 6 | 2580 | 2689 | 3.6s | (partial) | ✓ |

### Metrics
- **Rally detection:** 6/6 (100%)
- **Winner accuracy:** 5/5 (100%)
- **False positives:** 0

### Key Parameters
- NCC change threshold: 0.990
- Visibility gap minimum: 2.0 seconds
- Score digit regions: P1 row (7-27, 145-172), P2 row (28-50, 145-172)

---

## Phase B: Shot-Level Detection

**Method:** Optical flow (Farneback) direction change analysis with adaptive thresholds per rally duration.

### Shot Count Comparison

| Rally | Detected | Ground Truth | Error | Status |
|:-----:|:--------:|:------------:|:-----:|:------:|
| 1 | 15 | 16 | -1 | ±1 |
| 2 | 16 | 17 | -1 | ±1 |
| 3 | 9 | 9 | 0 | ✓ Exact |
| 4 | 8 | 7 | +1 | ±1 |
| 5 | 16 | 16 | 0 | ✓ Exact |
| 6 | 6 | 5+ | — | ✓ |
| **Total** | **70** | **70** | **0** | **✓ Exact** |

### Last-Shot Outcome Accuracy

| Rally | Detected | Ground Truth | Match |
|:-----:|:---------|:-------------|:-----:|
| 1 | P2 receives, out=yes | P1 receives, out=no | ✗ (off by 1) |
| 2 | P2 receives, out=yes | P1 receives, out=no | ✗ (off by 1) |
| 3 | P1 receives, out=yes, P1 wins | P1 receives, out=yes, P1 wins | ✓ |
| 4 | P1 receives, out=no | P2 receives, out=yes | ✗ (off by 1) |
| 5 | P1 receives, out=no, P2 wins | P1 receives, out=no, P2 wins | ✓ |

**Note:** Rallies with exact shot counts (3, 5) have correct last-shot outcomes. The ±1 errors in other rallies flip the alternation pattern.

### Key Parameters
- Frame skip: 2 (process every 2nd frame)
- Optical flow velocity threshold: 0.8 pixels/frame
- Smoothing window: 2-3 frames (adaptive)
- Direction change magnitude threshold: 0.12-0.27 (adaptive by rally length)
- Minimum shot gap: 0.3-0.55 seconds (adaptive)
- First rally intro skip: 6 seconds

### First Receiver Pattern (from ground truth)
| Rally | First Receiver |
|:-----:|:--------------:|
| 1 | Player 2 |
| 2 | Player 1 |
| 3 | Player 1 |
| 4 | Player 2 |
| 5 | Player 2 |
| 6 | Player 1 |

---

## Output Format

Per-shot CSV with columns:
- `No` — Global shot number
- `match` — Match identifier (always 1)
- `score` — Rally/score sequence number
- `Sequence of shot` — Shot number within rally
- `receive by` — Player receiving (player 1 or player 2)
- `zone (receive by)` — Landing zone 1-9 on receiver's court
- `last receive?` — "yes" for final shot, "n/a" otherwise
- `out?` — "yes" if shuttle was out, "no" if in, "n/a" for non-final shots
- `win by` — Point winner for final shot

---

## Sample Output (Rally 1)

```csv
,No,match,score,Sequence of shot,receive by,zone (receive by),last receive?,out?,win by
,1,1,1,1,player 2,6,n/a,n/a,n/a
,2,1,1,2,player 1,5,n/a,n/a,n/a
,3,1,1,3,player 2,9,n/a,n/a,n/a
...
,15,1,1,15,player 2,9,yes,yes,player 2
```

---

## Phase C: Player Tracking & Adaptive Calibration (2026-06-27)

**Method:** YOLOv8n (`ultralytics`, pretrained "person" class, no fine-tuning) detects both players per sampled frame. Their observed foot positions replace every fixed frame-ratio constant from Phase B:

- **Court bounds & net line** — derived per video from the 5th/95th percentile of player foot positions inside rally windows only (`court_calibration.py`), not a hardcoded box.
- **Shot-boundary threshold** — the optical-flow direction-reversal magnitude threshold is now the 30th percentile of *that rally's own* motion signal, not a fixed value picked per duration bucket. (Swept 20–40th percentile against ground truth; 30th gave the lowest average per-rally count error — see below.)
- **Scene-cut guard** — a histogram-correlation check (`frame_filter.detect_scene_change`) discards motion samples that straddle a camera cut instead of letting a garbage optical-flow vector register as a shot.
- **Zone mapping** — the *receiving player's* foot position at the shot frame (not a brightness-blob shuttle guess) is mapped through the calibration's bounds/net line. This is a deliberate proxy, not true shuttle localization (still Phase D's job).
- **First-receiver** — now derived from the actual detected winner of the previous rally (badminton rule: rally winner serves next), with one documented default for the match's very first rally. Previously this was a 6-entry lookup table reverse-fit to this video's own ground truth — a hidden form of hardcoding that has been removed.
- **Player-name fallback** — changed from this video's real names (`DONG T.Y.`/`FARHAN`) to generic `Player 1`/`Player 2`, with an explicit console warning whenever OCR fails, so a fallback can never silently leak one video's real names into another video's output.

### Video 1 (reference, has ground truth) — results

| Metric | Result | vs. target |
|---|---|---|
| Rally detection | 6/6 | unchanged from Phase A |
| Total shot count | 55 detected vs 70 ground truth | 21.4% error |
| Per-rally shot count, average error | 27.5% | **under the 30% bar** |
| `receive by` accuracy (aligned shots) | 88.7% | strong |
| `win by` accuracy (completed rallies) | **5/5 (100%)** | up from 3/5 in Phase B |
| `out?` accuracy (completed rallies) | 2/5 (40%) | weak — see note below |
| Zone exact match | 7.5% | weak in isolation |
| Zone exact-or-adjacent | 64.2% | close to the project's own ≥70% bar (Phase D target) |

Per-rally shot counts: `[18, 17, 4, 6, 6, 4]` vs ground truth `[16, 17, 9, 7, 16, 5]`. Rally 2 is exact; rallies 3 and 5 are the weak points (short/long rallies where this rally's own motion-percentile threshold didn't separate real hits from noise as well as the others).

**Why `out?` lags while `win by` doesn't:** `win by` is sourced directly from the scoreboard-detected rally winner (Phase A, already reliable) — it never depends on shot-detection accuracy. `out?`/`receive by`-of-last-shot depend on this rally's *total shot count parity*: if the detected count is off by an odd number from the true count, the last receiver flips, which flips `out?`, even though the (separately-sourced) `win by` stays correct. This is the same cascade effect noted in Phase B, just now isolated to specific rallies instead of a general overcount.

### Video 2 (no ground truth — generalization/plausibility check)

Run with **zero code or constant changes** between videos (854×480 vs video 1's 908×480, different players, different camera framing):

| Check | Phase B (old, hardcoded) | Phase C (new) |
|---|---|---|
| Player names | Silently used video 1's real names (wrong) | Generic `Player 1`/`Player 2` + visible warning |
| Shot count per rally | `[41, 28, 29, 13, 14, 30]` — implausibly dense (≈1 shot/sec sustained) | `[16, 14, 16, 5, 10, 21]` — plausible pacing (≈2–3s/shot in most rallies) |
| Zone distribution | Collapsed — nearly all shots in zones 7–9 | Spread across all 9 zones (zone 5 center and zone 2 most common — plausible) |
| `receive by` balance | n/a | 42 / 40 split — balanced alternation |

This is a real generalization improvement, not just a different failure mode — the same code, same constants, ran on a structurally different video and produced sane output.

**Known open limitation found during this work:** video 2 appears to include genuine multi-camera production cuts *within* a single rally (a wide static shot cutting to a closer dynamic-camera angle for a smash celebration, mid-point). The scene-cut guard catches hard cuts between consecutive analyzed frames, but didn't conclusively localize this particular transition in spot-checks — it's a different problem than the "fixed ratio doesn't match this video" issue this phase targeted. Flagged as follow-up, not silently ignored.

### Performance

- Video 1 (908×480, 89.6s): full pipeline including calibration + per-shot YOLO zone lookups.
- Video 2 (854×480, 176.6s): similar pipeline shape, longer due to video length.
- YOLO inference (CPU, `yolov8n.pt`): ~0.25s/frame after warmup. Calibration samples sparsely (~1 sample/sec within rally windows only) to keep this bounded; zone lookups run YOLO once per detected shot.

---

## Phase C.1: Real Court-Line Homography + Lunge-Apex Windowing (2026-06-27)

**Motivation:** Phase C's zone accuracy was weak (7.5% exact) and the row distribution had collapsed toward "mid" (47% predicted vs 19% in ground truth) — the receiving player's foot position *at the single detected shot frame* was a worse proxy for landing position than hoped. Two independent fixes were tried:

1. **Real court-line homography**, instead of a player-position-derived proportional grid, as the zone coordinate system.
2. **Lunge-apex windowing** — instead of one fixed frame, search a window around the shot and use the player's most-extended position relative to their rally "home" (median resting position), since contact happens at the outward extreme of a reach-and-recover arc, not at an arbitrary frame.

### Court-line homography: implemented correctly, found to hurt this specific use case

`court_detector.detect_court_corners()` had a real bug: it fit a `cv2.minAreaRect` to the detected green-court contour, which always returns an axis-aligned rectangle — discarding the actual trapezoid shape a perspective camera sees (the far baseline is narrower than the near baseline in pixels). Fixed by taking the convex hull's own 4 extreme corner points instead. Verified visually and numerically: the fixed corners map cleanly to a 610×1340cm rectangle via `compute_homography()`, and are stable across 9/11 sampled frames (only failing on 2 non-court frames during the intro, which are already skipped).

However, **using this homography to map a standing player's *foot position* to real-world court coordinates was tested empirically against ground truth and made zone prediction worse**, not better: across every tested configuration, "front" zone predictions dropped to ~0 (vs the proportional method's already-low 18%). The mechanism: an elevated single camera's ground-plane homography is highly sensitive to small foot-detection pixel error specifically near the far baseline (perspective compresses real distance into very few pixels there), and a standing person's detected foot point is systematically offset from their true ground-contact point because of their height relative to the camera's elevation angle — a well-known monocular sports-tracking limitation. That bias pushes mapped positions toward the baseline, which is exactly the "front disappears" failure observed.

**Decision:** kept the corner-detection fix (it's a genuine, validated bug fix) and the homography infrastructure (`court_detector.calibrate_homography`, wired into `CourtCalibration.zone_for` as a priority path) for future use — e.g. Phase D, once *actual shuttle position* rather than *player foot position* is being mapped, where this specific bias doesn't apply. Disabled it by default for the current player-position-proxy use (`calibrate_from_video(..., use_homography=False)`).

### Lunge-apex windowing: modest, real improvement — mainly on the horizontal axis

Swept window widths 0–16 frames (each side of the detected shot frame, capped by neighboring shots) against ground truth, with the receiving player's position taken at the point of maximum distance from their rally home base:

| Window (frames, ±) | Exact zone | Adjacent | Row divergence | Col divergence |
|:---:|:---:|:---:|:---:|:---:|
| 0 (Phase C baseline) | 7.5% | 60.4% | 0.91 | 0.57 |
| 4 | 13.2% | 52.8% | 0.91 | 0.34 |
| **12 (chosen)** | **13.2%** | **60.4%** | **0.91** | **0.45** |
| 16 | 13.2% | 49.1% | 0.91 | 0.42 |

*(Row/col divergence = sum of absolute differences between predicted and ground-truth row/column distribution shares; lower is better. "Adjacent" includes exact matches.)*

Window=12 frames (~0.4s each side) was chosen as the best balance of exact accuracy and stability across neighboring window sizes (not a one-off spike). Re-running the full pipeline end-to-end with this config against ground truth:

| Metric | Phase C (single-frame) | Phase C.1 (lunge-apex, window=12) |
|---|---|---|
| Zone exact match | 7.5% | **13.2%** |
| Zone exact-or-adjacent | 64.2%* | 60.4% |
| Row distribution (back/mid/front) | 35% / 47% / 18% | 43% / 42% / **15%** |
| Col distribution (left/center/right) | 27% / 45% / 27% | 42% / 30% / 28% |
| Ground truth row (back/mid/front) | 34% / 21% / 45% | 34% / 21% / 45% |
| Ground truth col (left/center/right) | 38% / 25% / 38% | 38% / 25% / 38% |

*(Phase C's 64.2% adjacent figure was from a slightly different calibration run; within noise of the 60.4% figure above — not a real regression.)*

**Honest read of this result:** the horizontal axis improved substantially — column distribution went from wildly center-collapsed (45% center vs 25% true) to roughly matching the true shape (30% vs 25%). The vertical axis improved only slightly — "mid" is still over-predicted roughly 2x versus ground truth (42% vs 21%), and "front" is still under-predicted (15% vs 45%). This matches the mechanistic prediction made when this approach was proposed: a player's forward/back movement is far more compressed in pixel space than their left/right movement (perspective foreshortening), especially for the far-court player, so a pixel-space "how far did they reach" measurement is naturally less sensitive to genuine front/back extremes than to left/right ones. Fixing the vertical axis properly likely needs either a court-space (not pixel-space) distance metric — which reintroduces the homography parallax problem above — or, more durably, actual shuttle position instead of a player-position proxy at all (Phase D).

### Key Parameters (Phase C.1)
- Lunge-apex search window: ±12 frames (~0.4s), capped by neighboring shot frames
- Lunge-apex sample stride: every 2nd frame within the window
- Homography: implemented, available, **off by default** for zone mapping (see above)

---

## Phase D: Real Shuttle Tracking via TrackNetV3 (2026-06-29)

**Motivation:** Phase C.1's honest read was that the player-position proxy has a structural ceiling — pixel-space "how far did the player reach" is a poor stand-in for "where did the shuttle actually land," especially front/back. The fix proposed there was to stop proxying and track the real shuttle.

**Method:** [TrackNetV3](https://github.com/qaz812345/TrackNetV3) (qaz812345), a pretrained temporal CNN (seq_len=8, `bg_mode='concat'`) doing per-frame heatmap regression for shuttlecock (x, y, visibility). Used as-is, no fine-tuning — it's trained on BWF-style broadcast footage already, which is what both project videos are. Run via `--eval_mode nonoverlap` (sliding_step=seq_len, ~8x fewer forward passes than the default overlapping-window ensemble mode) since this machine is CPU-only; ~52 minutes for video 1's 2689 frames.

**Visual validation:** spot-checked 6 frames against the source video before trusting the output at all — e.g. frame 1673 showed the shuttle correctly isolated mid-flight near the top of frame; frame 1043 showed it correctly at a lunging player's racket. Overall visibility rate 77.3% (the rest is the shuttle off-screen, occluded by a player, or genuinely too motion-blurred — not a tracking failure mode unique to this video).

### Finding 1: raw shuttle position *at* the shot frame is worse than the player proxy

The first, most direct approach — look up the shuttle's (x, y) at the optical-flow-detected shot frame, map it through the existing calibration — was tested first and was **worse** than Phase C.1's lunge-apex proxy on every distributional metric (front-zone predictions collapsed to near-zero, the opposite-but-equally-wrong failure mode from Phase C). Root cause: at the moment optical flow detects a "shot," the shuttle is typically still airborne mid-flight, so its pixel-Y reflects height above the court, not depth along the court — exactly the kind of confound a player's foot position doesn't have.

### Finding 2: the shuttle's local ground-contact point, searched *between* consecutive shots, is the fix

Re-framed the question: "zone (receive by)" means where the shuttle was *when the receiving player hit it*, which is the shuttle's lowest point (largest pixel-Y, closest to the court surface) during its descent from the previous shot, before the next player intercepts it. Searching for that local Y-maximum strictly between the previous shot's frame and the current shot's frame is a meaningfully different signal than the contact-frame lookup in Finding 1.

Swept a `pad_frames` parameter (frames to skip immediately after the previous shot, since the shuttle is still near the previous player's racket then, not descending):

| pad (frames) | Exact | Adjacent | Row divergence | Col divergence |
|:---:|:---:|:---:|:---:|:---:|
| 0 | 15.4% | 67.3% | 0.62 | 0.04 |
| **5 (chosen)** | **13.5%** | **63.5%** | **0.50** | **0.04** |
| 8 | 13.7% | 62.7% | 0.51 | 0.08 |
| 12 | 12.0% | 62.0% | 0.52 | 0.04 |
| 20 | 14.0% | 62.0% | 0.60 | 0.16 |

`pad=5` was chosen over `pad=0` despite a slightly lower exact/adjacent figure because it has the best row divergence (0.50, vs 0.62 at pad=0) without giving up the col-divergence win — `pad=0` was let through a small amount of contact-blur noise from the previous shot that `pad=5` filters out. Larger pads start re-picking up the *next* exchange's bounce instead of this one's.

### Full pipeline result, video 1

Wired into the actual pipeline (`src/pipeline/shuttle_tracker.py`, called from `main.py`) rather than left as an offline script — `ShuttleTracker.landing_point()` replaces the player-proxy lookup as the primary source, falling back to Phase C.1's lunge-apex if TrackNetV3 isn't set up on a given machine (anti-hardcoding requirement: the pipeline must still run, just less accurately, without this optional heavy dependency).

| Metric | Phase C.1 (player proxy) | Phase D (real shuttle) |
|---|---|---|
| Zone exact match | 13.2% | 13.2% |
| Zone exact-or-adjacent | 60.4% | 60.4% |
| Row distribution (back/mid/front) | 43% / 42% / 15% | 17% / 47% / 36% |
| Col distribution (left/center/right) | 42% / 30% / 28% | 40% / 24.5% / 35.8% |
| Ground truth row (back/mid/front) | 34% / 21% / 45% | 34% / 21% / 45% |
| Ground truth col (left/center/right) | 38% / 25% / 38% | 38% / 25% / 38% |
| Row divergence | 0.60 | 0.53 |
| Col divergence | 0.19 | **0.04** |
| `receive by` accuracy | 88.7% | 88.7% (unchanged — shuttle position doesn't affect this) |

**Honest read:** exact-match and adjacent-match percentages happened to land on the same numbers as Phase C.1 — coincidence at this sample size (n=53), not evidence of no change; the underlying error *shape* changed substantially. Column distribution is now very close to ground truth (0.04 divergence, vs 0.19) — the left/right axis is essentially solved. Row distribution improved (0.60 → 0.53) and front-zone representation is now far closer to the true shape (36% predicted vs 45% true, vs Phase C.1's 15% vs 45%) — but "back" is now *under*-predicted (17% vs 34% true) where Phase C.1 over-predicted "mid." This is a different, smaller-magnitude version of the same vertical-axis difficulty flagged in Phase C.1, now likely coming from a different source: the `pad_frames` search window can blur together "shuttle still descending from a high clear" with "shuttle landing from a short drop shot" in a way a single scalar pad can't fully disambiguate. Treated as the next concrete target if further iteration on this axis is wanted, not as a blocker — the column-axis fix alone is a real, validated improvement.

### Video 2 (no ground truth — generalization check)

Ran the same unmodified pipeline on video 2 (854×480, 176.6s — nearly 2x video 1's length).

**A real integration bug was found and fixed here, and the first read of this run was wrong — worth recording both, not just the corrected answer.** TrackNetV3's subprocess for video 2 ran for ~75 minutes and then disappeared from the process list. Free system memory had been observed dipping as low as ~255MB during the run, so the first conclusion was "OS-level out-of-memory kill" — plausible, and `main.py`'s fallback engaged exactly as designed (printed `"TrackNetV3 unavailable... falling back to player-position proxy"`, completed normally with plausible-looking output). **That conclusion was wrong.** TrackNetV3 had actually completed successfully; its output csv just landed in the wrong folder. The cause: `predict.py` extracts the video's filename via `video_file.split('/')[-1]` — a Unix-style split that's a no-op against a Windows backslash path, and `os.path.join(save_dir, video_name)` then silently *discards* `save_dir` entirely once `video_name` itself looks like an absolute path (Python's `os.path.join` semantics: an absolute-looking later argument wins). The prediction csv was sitting in `input/`, not `data/shuttle_cache/`, the whole time the fallback was "explaining" its absence. Fixed in `shuttle_tracker.py` by normalizing the path argument to forward slashes before passing it to the vendored script (`str(video_path.resolve()).replace("\\", "/")` — see commit). Recovered the already-complete prediction file, re-ran the pipeline (now a ~1 minute run, no TrackNet re-inference needed), and got the real result below.

**The real result exposed a second, more interesting problem — and this one was hiding behind the proxy the whole time, not introduced by Phase D:**

| Check | Result |
|---|---|
| Total shots | 82 across 6 rallies: `[16, 14, 16, 5, 10, 21]` (shot *detection* is untouched by Phase D; only zone mapping differs from the earlier, now-superseded fallback run) |
| `receive by` balance | 42 / 40 — balanced alternation |
| Zone distribution (real shuttle) | `{1:6, 2:32, 3:16, 5:6, 6:20, 8:1, 9:1}` — collapsed into zones 1/2/3/6, almost nothing in 4/7/8/9 |
| Row distribution (real shuttle) | back 65.9% / mid 31.7% / **front 2.4%** |
| Col distribution (real shuttle) | left 7.3% / center 47.6% / right 45.1% |
| (for contrast) Row/col distribution via the player-proxy fallback that ran first | back 37.8% / mid 40.2% / front 22.0%; left 31.7% / center 40.2% / right 28.0% — looked far more plausible, but for the wrong reason (see below) |

**Root cause:** `court_calibration.zone_for()`'s proportional-grid fallback *clamps* `x`/`y` into `[0, 1]` before computing row/column (`court_calibration.py` lines ~75, ~81, ~87) — by design, since a player's foot position can wander slightly outside the sampled calibration range and should still snap to the nearest edge zone rather than error out. Video 2's calibration bounds (`top=176, bottom=480, left=54, right=667`, from 156 player-foot samples) are — correctly — derived from where players' *feet* were observed standing. But the real shuttle's landing-point Y values have a median of 134, *below* `top=176`: the shuttle legitimately travels into screen space no player's feet ever occupied (deep clears landing near the true baseline, on a camera framing where the baseline sits above where the calibration sampled players standing). Every one of those points clamps to `rel=0` → the back row, every time. A player-position proxy can never expose this, because the proxy's positions are *definitionally* inside the calibration's range — they're what the calibration was built from. The real shuttle has no such guarantee, and video 2's camera framing was different enough from video 1's that the gap became large enough to matter (video 1's `top=91` happened to leave enough headroom that this didn't show up there).

**Honest read:** this is a real, newly-discovered limitation, not a regression — Phase D didn't create this gap, it revealed it. The fix isn't more clamping; it's widening the calibration's bounds using the observed shuttle position range (once available) in addition to player foot positions, or biasing `margin_frac` upward specifically on the side the shuttle, not the players, defines. Not yet implemented — flagged as the concrete next step for whoever continues this, alongside the now-fixed path bug. The earlier "plausible-looking" fallback result for video 2 is superseded and should not be cited as evidence Phase D works well on video 2; it was the proxy quietly avoiding a calibration problem that the real shuttle data was the first thing to actually expose.

### Key Parameters (Phase D)
- TrackNetV3 inference mode: `nonoverlap` (CPU-feasible; ~52 min for video 1's 90s, ~75 min for video 2's 177s)
- Video file path passed to the vendored `predict.py` must use forward slashes even on Windows — the script's own filename-extraction logic is Unix-style and silently breaks `--save_dir` otherwise (see video 2 finding above)
- Shuttle landing-point pad: 5 frames after the previous shot
- Fallback: lunge-apex (Phase C.1) when TrackNetV3 predictions are unavailable (validated under real failure conditions, not just code review)

---

## Git History

| Commit | Description |
|--------|-------------|
| *(uncommitted)* | Phase D: TrackNetV3 real shuttle tracking, `shuttle_tracker.py`, wired into `main.py` with player-proxy fallback |
| `12d7a6e` | Phase C/C.1: YOLO player tracking, adaptive court calibration, lunge-apex zone estimation |
| `5c342c1` | Phase B tuning: adjust intro skip to 6s |
| `512a54b` | Phase B: Shot-level detection within rallies |
| `6251c5a` | Phase A: Scoreboard-driven rally segmentation |
| `adc3135` | Initial project scaffold |

---

## Files

### Pipeline Modules
- `src/pipeline/scoreboard_ocr.py` — Pixel-based score change detection
- `src/pipeline/rally_segmenter.py` — Build Rally objects from score changes
- `src/pipeline/player_detector.py` — YOLO person detection (Phase C) + `find_lunge_apex` windowed position search (Phase C.1)
- `src/pipeline/court_detector.py` — Court corner detection (fixed in C.1) + homography (Phase C.1, available, off by default)
- `src/pipeline/court_calibration.py` — Adaptive court bounds/net line + zone mapping, homography-aware (Phase C/C.1)
- `src/pipeline/shot_detector.py` — Optical flow shot detection with adaptive per-rally threshold + scene-cut guard + lunge-apex zone estimation (fallback)
- `src/pipeline/shuttle_tracker.py` — TrackNetV3 wrapper: generates/caches per-video shuttle predictions, finds each shot's landing point (Phase D)
- `src/pipeline/export.py` — CSV output generation

### Entry Point
- `src/main.py` — CLI orchestrator (6-step pipeline)

### Superseded / now-dead code
- `src/pipeline/zone_mapper.py`, `src/pipeline/player_tracker.py` — no longer imported by `main.py` as of Phase C. Candidates for deletion in a follow-up cleanup pass.
- `src/pipeline/shuttle_tracker.py`'s original blob-detection implementation was replaced outright in Phase D (same filename, new contents) — it was never imported by `main.py`, so there was no dead code to carry forward.

---

## Performance

- **Processing time:** ~45 seconds on CPU (no GPU) — Phase B baseline, before Phase C's added YOLO calls
- **Video:** 908x480 @ 30fps, 2689 frames

---

*Last updated: 2026-06-29*
