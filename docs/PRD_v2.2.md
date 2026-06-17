# Badminton Video Analysis Service — PRD v2.2

> **Version:** 2.2 — Per-Shot Analysis with Iterative Improvement Plan  
> **Status:** Active  
> **Author:** Jayson Fetra  
> **Date:** 16 June 2026  
> **Platform:** Backend Python service (CLI)  
> **Supersedes:** PRD v2.0, v2.1

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

### 5.3 Input Method

- User places MP4 file in `input/` folder (or specifies path via CLI argument)
- Service validates file size and duration before processing
- If validation fails, service exits with descriptive error message

### 5.4 Ground Truth / Validation Data

Reference ground truth file: `badminton_video_result.csv`
- 70 shots across 6 rallies (scores) in the example 55-second video
- Rally lengths: 16, 17, 9, 7, 16, 5+ shots
- Score progression: Player 2 wins scores 1, 2; Player 1 wins score 3; Player 2 wins score 4; Player 2 wins score 5; score 6 partial

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
| 7. Shuttle Tracking | Track shuttle position frame-by-frame within rallies | Detect individual shot exchanges |
| 8. Shot Detection | Identify each individual hit/exchange | One shot = shuttle going from one side to the other |
| 9. Player Attribution | Determine who received each shot | Alternate assignment based on shot sequence |
| 10. Zone Mapping | Map shuttle landing coordinates to zones 1–9 | Fill "zone (receive by)" column |
| 11. Last-Shot Logic | Apply badminton rules to determine winner/out | Fill last_receive, out, win_by columns |
| 12. Output Generation | Write per-shot CSV | Deliver final results |

### 7.3 Folder Structure

```
badminton-video-analysis/
├── input/                  # Place video files here
├── output/                 # Analysis results written here
├── src/
│   ├── main.py            # CLI entry point & pipeline orchestrator
│   ├── config.py          # Configuration constants
│   ├── pipeline/
│   │   ├── validator.py       # Input validation
│   │   ├── court_detector.py  # Court detection & homography
│   │   ├── frame_filter.py    # Non-play frame detection
│   │   ├── scoreboard_ocr.py  # Player names + score extraction
│   │   ├── rally_segmenter.py # Rally boundary detection
│   │   ├── shuttle_tracker.py # Shuttle position tracking (upgradeable to TrackNet)
│   │   ├── shot_detector.py   # Individual shot/exchange detection
│   │   ├── player_tracker.py  # Player position & attribution
│   │   ├── zone_mapper.py     # Coordinate → zone mapping
│   │   └── outcome_logic.py   # Last-shot winner/out determination
│   ├── models/                # ML model weights (TrackNet, YOLO, etc.)
│   └── utils/
│       └── export.py          # CSV output generation
├── tests/
│   └── test_against_ground_truth.py  # Validation against reference CSV
├── data/
│   ├── ground_truth/          # Reference CSVs for validation
│   └── models/                # Downloaded model weights
├── docs/
│   └── PRD_v2.2.md
├── requirements.txt
└── pyproject.toml
```

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
  player1_name: "DONG T.Y."    # Far court (top of frame); fallback if OCR fails
  player2_name: "FARHAN"       # Near court (bottom of frame); fallback if OCR fails

processing:
  confidence_threshold: 0.5
  frame_skip: 2
```

---

## 9. Iteration Plan

### Prerequisite: Badminton Rules Understanding

Before any phase begins, engineering must internalize the rules documented in Section 4. Key logic that depends on rules:
- Shot alternation (Player A → Player B → Player A → ...)
- Score change = rally boundary
- Service = first shot of every rally
- Last-shot outcome logic (in/out determination)

### Phase A — Fix Rally Segmentation (Scoreboard-Driven)

**Goal:** Correctly detect all rallies using scoreboard OCR as primary boundary signal.

**Approach:**
1. Sample scoreboard region every 0.5s
2. OCR the score digits
3. Detect score changes (temporal smoothing across multiple frames)
4. Each confirmed score change = one rally boundary
5. Optionally confirm with motion detection (serve = high motion at start)

**Acceptance Criteria:**
- Detect ≥80% of rallies in the reference video (at least 5 of 6 score sequences)
- No false-positive rallies (spurious score readings filtered)
- Player names extracted from scoreboard with ≥80% character accuracy

**Does NOT require:** TrackNet, shuttle tracking, or shot-level detection.

**Output at this phase:** Rally-level output only (score sequence boundaries).

---

### Phase B — Shot-Level Tracking (Within Rally)

**Goal:** Detect each individual shot exchange within a rally.

**Approach:**
1. Within each rally's frame range, track shuttle position frame-by-frame
2. Detect shot exchanges: shuttle crosses from one court half to the other = 1 shot
3. Apply alternation rule: shots must alternate between players
4. Count shots per rally and compare against ground truth
5. Use player position + shuttle trajectory direction to determine "receive by"

**Acceptance Criteria:**
- Detect ≥80% of shots within detected rallies (compare shot count per rally vs ground truth)
- Correct player alternation on ≥90% of detected shots
- Shot count per rally within ±2 of ground truth for ≥80% of rallies

**Key challenge:** Shuttle is very small and fast in broadcast footage. Initial approach uses blob detection + motion; upgraded approach uses TrackNet.

---

### Phase C — Integrate TrackNet for Shuttle Detection

**Goal:** Replace basic blob detection with a specialized shuttle detection model for higher accuracy.

**Approach:**
1. Download/integrate TrackNetV3 pre-trained weights for badminton
2. Run TrackNet on rally frames to get per-frame shuttle (x, y) coordinates
3. Use TrackNet trajectory to more accurately detect:
   - Shot exchanges (direction changes in shuttle trajectory)
   - Landing positions (trajectory endpoints)
4. Optionally add YOLOv7/v8 for player position detection (improves attribution)

**Acceptance Criteria:**
- Shuttle detection rate ≥80% of frames within rallies
- Shot count accuracy improves to within ±1 of ground truth for ≥80% of rallies
- Zone accuracy ≥80% compared to ground truth (correct zone or adjacent zone)

**Research References:**
| Paper | Contribution |
|-------|-------------|
| TrackNetV3 | Frame-level shuttle (x,y) detection model for badminton |
| Sensors 2024 (TrackNet + YOLOv7) | Combined shuttle + player detection; hit detection pipeline |
| ShuttleSet (KDD 2023) | Best public annotated dataset; defines annotation schema |
| CoachAI Challenge 2023 | 11-task benchmark including rally segmentation and zone prediction |
| Court to Conversation (2025) | End-to-end system reference architecture including LLM querying |

---

### Phase D — Last-Shot Outcome Logic & Output Polish

**Goal:** Apply badminton rules to determine point winner and in/out for each rally's final shot.

**Approach:**
1. For each rally, identify the last detected shot
2. Determine who received it (player attribution)
3. Cross-reference with scoreboard: who got the point?
4. Apply rules:
   - Last receiver ≠ point winner → shuttle was IN (not out), receiver failed
   - Last receiver = point winner → shuttle was OUT, hitter's shot landed outside
5. Generate final per-shot CSV output

**Acceptance Criteria:**
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
| AC-12 | Player names extracted from scoreboard match "DONG T.Y." and "FARHAN". |
| AC-13 | Service completes processing of a 20-min video within 30 min on consumer hardware. |
| AC-14 | Non-play frames (replays, crowd shots) do not generate false shot data. |

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Shuttle too small/fast to track in broadcast video | Cannot detect individual shots | Use TrackNet (Phase C); accept lower per-shot accuracy in Phase B |
| Scoreboard OCR unreliable | Rally boundaries missed; wrong player names | Temporal smoothing; sample multiple frames; fallback to manual config |
| Rally detector misses points | Output has fewer rallies than actual | Scoreboard score changes are mandatory events; flag gaps |
| Camera cuts mid-rally (replays) | False shot detections | Frame filtering; detect scene changes and skip |
| Homography inaccurate | Zones misattributed | Per-video calibration; larger zone tolerance (adjacent = acceptable) |
| TrackNet model unavailable or incompatible | Phase C blocked | Phase B blob detection provides baseline; source model from public repos |
| Shot count mismatch | More/fewer shots than ground truth | Cross-validate with alternation rule; flag anomalies |

---

## 12. Success Metrics

| Metric | Phase A Target | Phase B Target | Phase C Target | Phase D Target |
|--------|---------------|---------------|---------------|---------------|
| Rally detection | ≥80% (5/6) | ≥80% | ≥90% | ≥90% |
| Shot count accuracy | n/a | ±2 per rally | ±1 per rally | ±1 per rally |
| Zone accuracy | n/a | ≥50% | ≥70% | ≥80% |
| Receive-by accuracy | n/a | ≥80% | ≥90% | ≥90% |
| Win-by accuracy | ≥80% | ≥80% | ≥80% | ≥90% |
| Player name extraction | ≥80% | ≥80% | ≥90% | ≥90% |
| Processing time | <1min | <3min | <5min | <5min |

---

## 13. Open Questions

| # | Question | Proposed Answer |
|---|----------|----------------|
| 1 | What if TrackNet pre-trained weights don't work well on this broadcast style? | Fine-tune on ShuttleSet dataset or annotate a few frames manually |
| 2 | Should we support variable camera angles across different tournaments? | v1: optimize for BWF-style broadcasts only; generalize later |
| 3 | How to handle rallies that span camera cuts (replay inserted mid-rally)? | Detect scene change → pause tracking → resume when court returns |
| 4 | What if scoreboard is obscured or has different format? | Allow manual player-name and score override via config |
| 5 | Should aggregate reports (per-point summary) be a separate command? | Yes — derive from per-shot CSV; implement post-Phase D |

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
| 1st | TrackNetV3 | Shuttle detection model — core tracking capability |
| 2nd | Sensors 2024 (TrackNet + YOLOv7) | Combined shuttle + player detection pipeline |
| 3rd | ShuttleSet (KDD 2023) | Best public dataset; defines annotation schema |
| 4th | CoachAI Challenge 2023 | 11-task benchmark to build toward |
| 5th | Court to Conversation (2025) | Full end-to-end system with LLM querying |

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
