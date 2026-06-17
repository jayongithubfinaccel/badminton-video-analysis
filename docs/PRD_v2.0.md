# Badminton Video Analysis Service — PRD v2.1

> **Version:** 2.1 — Automated Analysis Pipeline + Scoreboard Extraction Improvements  
> **Status:** Draft  
> **Author:** Jayson Fetra  
> **Date:** 16 June 2026  
> **Platform:** Backend Python service (CLI)

---

## 1. Overview

This is a **backend-only Python service** that automatically analyzes badminton match video from broadcast footage and produces structured data about each rally — including score progression, shuttle landing zones (9-zone grid), and shot outcomes.

The user places an MP4 video file in an input folder, runs the service, and receives an Excel/CSV output file containing per-point statistics: who scored, cumulative score, shuttle landing distribution across 9 court zones for each player, and the zone of the winning/losing shot.

No frontend. No manual annotation. Fully automated via computer vision.

---

## 2. Problem Statement

Manually annotating badminton match videos is time-consuming (a 20-minute video can take 2+ hours to annotate shot by shot). Coaches and analysts need structured match data — zone heatmaps, shot patterns, scoring sequences — but lack an automated tool that can extract this from readily available broadcast footage.

This service automates the data collection pipeline: video in → structured data out.

---

## 3. Goals and Non-Goals

### 3.1 Goals

- Automatically detect rallies (play start/stop) from broadcast badminton video
- Track shuttle landing positions and map them to a 9-zone court grid
- Identify which player hit the shuttle and attribute shots per player
- Detect rally outcomes (who won each point)
- Track cumulative score progression across the match
- Extract player names from the broadcast scoreboard overlay
- Detect every visible scoreboard score change in the input video, including points where rally segmentation confidence is low
- Output results in Excel format matching the defined template
- Run as a simple CLI: input video → output Excel file

### 3.2 Non-Goals (v1)

- No frontend / UI / web interface
- No real-time / streaming analysis (batch processing only)
- No doubles match support
- No shot-type classification (e.g., smash vs drop) — only landing zone
- No cloud deployment — local execution only
- No video editing or highlight generation

---

## 4. User Stories

| ID | User Story | Acceptance Criteria | Priority |
|----|-----------|---------------------|----------|
| US-01 | As an analyst, I want to place a video file in an input folder and run a single command to get analysis results. | Running `python analyze.py` (or equivalent) processes the video and produces output in the configured output folder. | P0 |
| US-02 | As an analyst, I want the service to detect each rally (sequence of play) automatically. | Service identifies rally start (serve) and rally end (point scored) with ≥80% accuracy. | P0 |
| US-03 | As an analyst, I want to know which player won each point and the cumulative score. | Output includes point winner and running score for both players, matching broadcast scoreboard. | P0 |
| US-04 | As an analyst, I want shuttle landing zones (1–9) tracked for each player per rally. | For each point, output shows how many times the shuttle landed in each of the 9 zones for Player 1 and Player 2. | P0 |
| US-05 | As an analyst, I want to know the zone of the winning/losing shot for each point. | Output includes a "winning shot zone" column for the scoring player and "losing shot zone" for the other. | P0 |
| US-06 | As an analyst, I want the output in Excel (.xlsx) format matching my template. | Output file structure matches the defined template (see Section 6.2). | P0 |
| US-07 | As an analyst, I want the service to reject videos that exceed size/duration limits. | Videos >100MB or >20 minutes are rejected with a clear error message. | P1 |
| US-08 | As an analyst, I want the service to handle match sets (Game 1, 2, rubber). | Output distinguishes which game/set each point belongs to. | P1 |
| US-09 | As an analyst, I want the service to ignore non-court content (replays, crowd shots, ads). | Service only processes frames where active court play is visible. | P1 |
| US-10 | As an analyst, I want a confidence score for each detected point. | Output includes a confidence column so I know which rows may need manual review. | P2 |
| US-11 | As an analyst, I want the service to extract player names from the video scoreboard. | Output column headers and point winner values use detected player names when OCR confidence is sufficient. | P0 |
| US-12 | As an analyst, I want all scoreboard score changes in the video reflected in the output. | If the video scoreboard progresses to 4 total points, the output must include 4 point rows or clearly flag missing/uncertain points. | P0 |

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

Based on the reference video (BWF World Tour style):
- Camera positioned behind and above one end of the court
- Perspective angle shows full court with foreshortening
- Scoreboard overlay in corner (player names + score), typically top-left for the reference video
- Sponsor banners, crowd, and non-court elements surround the playing area
- Occasional camera cuts to replays, close-ups, or crowd (to be ignored)
- Court lines clearly visible (white/yellow lines on green/blue surface)

### 5.3 Input Method

- User places MP4 file in `input/` folder (or specifies path via CLI argument)
- Service validates file size and duration before processing
- If validation fails, service exits with descriptive error message

### 5.4 Scoreboard Extraction Requirements

The service must treat the broadcast scoreboard as the primary source of truth for:

- Player names
- Current game score
- Score progression / point count

For the reference video, the scoreboard shows the player names **Dong T.Y.** and **Farhan** and the score progresses beyond the first 2 points. The service must not stop output at the first two detected rallies if the scoreboard indicates additional points were played or shown.

If scoreboard OCR detects a score change but rally/shuttle tracking cannot confidently reconstruct the rally, the output must still include a point row with:

- Correct point winner inferred from the score change
- Correct cumulative score
- Zone counts set to blank or `0` depending on confidence
- Confidence marked below threshold
- A review flag indicating the row needs manual validation

---

## 6. Output Specifications

### 6.1 Output Method

- Results written to `output/` folder as `.xlsx` file
- Filename: `{input_video_name}_analysis_{timestamp}.xlsx`
- One worksheet per game/set in the match

### 6.2 Output Template (Excel Columns)

| Column | Field | Description |
|--------|-------|-------------|
| A | No | Point number (sequential, resets per game) |
| B | Point Winner | Who obtained the score: detected player name when available; otherwise "Player 1" or "Player 2" |
| C | Game | Which game: 1, 2, or 3 (rubber) |
| D | Player 1 Score | Cumulative score for Player 1 after this point; header should use detected player name when available |
| E | Player 2 Score | Cumulative score for Player 2 after this point; header should use detected player name when available |
| F | Rally Shot Count | Total number of shots in this rally |
| G–O | Player 1 Zone 1–9 | Number of shots landing in each zone (1–9) for Player 1's court half during this rally |
| P | Player 1 Win/Lose Zone | The zone where the winning or losing shot landed on Player 1's court |
| Q–Y | Player 2 Zone 1–9 | Number of shots landing in each zone (1–9) for Player 2's court half during this rally |
| Z | Player 2 Win/Lose Zone | The zone where the winning or losing shot landed on Player 2's court |
| AA | Confidence | Detection confidence score (0.0–1.0) for this point |
| AB | Review Flag | `OK`, `LOW_CONFIDENCE`, `SCORE_ONLY`, or `MISSING_RALLY_CONTEXT` |

### 6.3 Zone Definition (9-Zone Court Grid)

Each player's half of the court is divided into a 3×3 grid (9 zones). Zone numbering follows the reference image (`badminton_court_9zone.png`):

```
┌─────────────────────────────┐
│  Baseline (Back of court)   │
├─────────┬─────────┬─────────┤
│  Z1     │  Z2     │  Z3     │  ← Back row
│  (Back  │  (Back  │  (Back  │
│   Left) │  Center)│  Right) │
├─────────┼─────────┼─────────┤
│  Z4     │  Z5     │  Z6     │  ← Mid row
│  (Mid   │  (Mid   │  (Mid   │
│   Left) │  Center)│  Right) │
├─────────┼─────────┼─────────┤
│  Z7     │  Z8     │  Z9     │  ← Front row
│  (Front │  (Front │  (Front │
│   Left) │  Center)│  Right) │
├─────────┴─────────┴─────────┤
│          NET                │
└─────────────────────────────┘
```

- **Z1–Z3 (Back row):** Near the baseline
- **Z4–Z6 (Mid row):** Middle of the half-court
- **Z7–Z9 (Front row):** Near the net
- Left/Right is from the **player's own perspective** facing the net

Each player's court half has its own independent 9-zone grid. Shuttle landing is attributed to the **receiver's** court half (where the shuttle lands).

---

## 7. Technical Architecture (High-Level)

> **Note:** Technology decisions to be finalized with Senior Engineer. This section describes the required capabilities, not implementation specifics.

### 7.1 Pipeline Stages

```
┌──────────┐    ┌──────────────┐    ┌───────────────┐    ┌──────────────┐    ┌────────────┐
│  Input   │───►│  Court       │───►│  Rally        │───►│  Shuttle     │───►│  Output    │
│  Video   │    │  Detection   │    │  Segmentation │    │  Tracking &  │    │  Generator │
│  (.mp4)  │    │  & Homography│    │  (play/stop)  │    │  Zone Mapping│    │  (.xlsx)   │
└──────────┘    └──────────────┘    └───────────────┘    └──────────────┘    └────────────┘
                                                                │
                                                         ┌──────┴───────┐
                                                         │  Score       │
                                                         │  Tracking    │
                                                         └──────────────┘
```

### 7.2 Required Capabilities

| Stage | Capability | Purpose |
|-------|-----------|---------|
| 1. Validation | File size/duration check | Reject invalid inputs early |
| 2. Court Detection | Detect court boundaries in broadcast frame | Establish coordinate system |
| 3. Homography | Perspective transform to top-down view | Map pixel coords to court positions |
| 4. Frame Filtering | Detect non-play frames (replays, ads, crowd) | Only analyze active play |
| 5. Rally Segmentation | Detect serve → point-end boundaries | Split video into rally units |
| 6. Shuttle Tracking | Track shuttle position frame-by-frame | Determine landing positions |
| 7. Player Attribution | Identify which player hit / received | Attribute zones to correct player |
| 8. Zone Mapping | Map landing coordinates to zones 1–9 | Fill zone count columns |
| 9. Score Tracking | OCR scoreboard and infer fallback from rally wins | Cumulative score per point |
| 10. Player Name Extraction | OCR player names from scoreboard region | Use real player names in output |
| 11. Score/Rally Reconciliation | Compare detected score changes vs detected rallies | Prevent missing points when scoreboard shows more scores than rally detector found |
| 12. Output Generation | Write structured Excel file | Deliver final results |

### 7.3 Folder Structure

```
badminton-video-analysis/
├── input/                  # Place video files here
├── output/                 # Analysis results written here
├── src/
│   ├── main.py            # CLI entry point
│   ├── pipeline/
│   │   ├── validator.py       # Input validation (size, duration, format)
│   │   ├── court_detector.py  # Court line detection & homography
│   │   ├── frame_filter.py    # Filter non-play frames
│   │   ├── rally_segmenter.py # Rally start/end detection
│   │   ├── shuttle_tracker.py # Shuttle position tracking
│   │   ├── player_tracker.py  # Player identification & attribution
│   │   ├── zone_mapper.py     # Map coordinates to 9-zone grid
│   │   └── score_tracker.py   # Score detection/tracking
│   ├── models/                # ML model weights & configs
│   ├── utils/
│   │   └── export.py          # Excel output generation
│   └── config.py             # Configuration constants
├── tests/
├── data/                   # Reference data, model weights
├── docs/
│   └── PRD_v2.0.md
├── requirements.txt
└── pyproject.toml
```

---

## 8. Configuration

```yaml
# config.yaml (or constants in config.py)
input:
  max_file_size_mb: 100
  max_duration_minutes: 20
  supported_formats: [".mp4"]
  input_folder: "./input"

output:
  output_folder: "./output"
  format: "xlsx"

processing:
  min_resolution: 720
  confidence_threshold: 0.5  # Below this, flag for manual review
```

---

## 9. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-01 | Service processes a valid MP4 file (≤100MB, ≤20min) without errors. |
| AC-02 | Service rejects files >100MB with error: "File exceeds 100MB limit." |
| AC-03 | Service rejects files >20min with error: "Video exceeds 20-minute limit." |
| AC-04 | Service rejects non-MP4 files with error: "Only MP4 format supported." |
| AC-05 | Output Excel file contains all columns defined in Section 6.2. |
| AC-06 | Zone numbering matches the reference image (Z1–Z3 back, Z7–Z9 front). |
| AC-07 | Cumulative score in output is correct and sequential. |
| AC-08 | Each point row includes zone counts for both players. |
| AC-09 | Winning/losing shot zone column is populated for each point. |
| AC-10 | Non-play frames (replays, crowd shots) do not generate false rally data. |
| AC-11 | Service completes processing of a 20-min video within reasonable time (<30 min on consumer hardware with GPU). |
| AC-12 | Output filename includes source video name and processing timestamp. |
| AC-13 | Player names are extracted from the scoreboard when visible with sufficient OCR confidence. |
| AC-14 | For the reference video, if the visible scoreboard reaches 4 total points, the output contains 4 point rows or flags the missing points as score-only rows. |
| AC-15 | Output includes a review flag for rows where score was detected but rally/shuttle details are incomplete. |

---

## 10. Milestones and Phasing

| Phase | Scope | Rationale |
|-------|-------|-----------|
| **Phase 1 — Foundation** | Input validation, court detection, homography transform, basic frame output | Establish the coordinate system — everything depends on accurate court mapping |
| **Phase 2 — Rally Detection** | Frame filtering (play vs non-play), rally segmentation (serve to point-end) | Must isolate rallies before tracking shots within them |
| **Phase 3 — Shuttle Tracking** | Shuttle detection & tracking, landing position estimation, zone mapping | Core analysis capability — map shuttle to 9-zone grid |
| **Phase 4 — Scoreboard Extraction & Reconciliation** | Player-name OCR, score OCR, score-change detection, reconciliation between scoreboard points and detected rallies | Prevent missing points and use real player names |
| **Phase 5 — Output** | Player attribution, Excel output generation, review flags | Assemble all data into the final output format |
| **Phase 6 — Accuracy & Polish** | Confidence scoring, edge case handling, performance optimization | Improve reliability for production use |

---

## 11. Risks and Mitigations

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Shuttle too small/fast to track in broadcast video | Core feature fails | Use specialized models (TrackNet v2/v3); accept lower accuracy for fast exchanges |
| Camera angle changes mid-rally (broadcast cuts) | False data during replays | Frame filtering stage must detect and skip non-standard frames |
| Scoreboard OCR unreliable across different broadcasts | Incorrect score tracking and player names | Calibrate scoreboard region per video; sample multiple frames; use temporal smoothing; fall back to configured player names if OCR confidence is low |
| Rally detector misses points that scoreboard shows | Output has fewer rows than actual score progression | Treat scoreboard score changes as mandatory point events; generate score-only rows when rally context is missing |
| Homography inaccurate due to lens distortion | Zones misattributed | Calibrate per-video; use multiple court reference points |
| Processing time too long for 20-min video | Poor user experience | GPU acceleration; process at reduced frame rate for non-critical stages |

---

## 12. Open Questions

| # | Question | Proposed Answer |
|---|----------|----------------|
| 1 | Should player names be auto-detected from scoreboard OCR or manually specified? | Auto-detect from scoreboard first; allow manual override if OCR confidence is low |
| 2 | What accuracy threshold is acceptable for zone mapping? | ≥70% correct zone assignment for v1 (adjacent zone errors acceptable) |
| 3 | Should the service process multiple videos in batch? | v1: one video at a time; batch mode as future enhancement |
| 4 | How to handle points where shuttle tracking confidence is low? | Output the row with confidence < threshold; flag for manual review |
| 5 | Should the output include timestamps for each point? | Yes — include video timestamp of rally start for cross-reference |

---

## 13. Success Metrics

| Metric | Target (v1) |
|--------|-------------|
| Rally detection accuracy | ≥ 80% of rallies correctly segmented |
| Zone mapping accuracy | ≥ 70% of shots mapped to correct zone |
| Score tracking accuracy | ≥ 90% of points with correct cumulative score |
| Player-name extraction accuracy | ≥ 90% on supported BWF-style scoreboard overlays |
| Score coverage | 100% of visible scoreboard score changes represented as output rows, with low-confidence rows flagged |
| Processing time | ≤ 1.5× video duration on GPU-equipped machine |
| False positive rate | < 10% spurious rally detections |

---

## Appendix A — Output Example

For a point where Player 1 (Farhan) wins, rally had 6 shots:

| No | Point Winner | Game | P1 Score | P2 Score | Rally Shots | P1-Z1 | P1-Z2 | P1-Z3 | P1-Z4 | P1-Z5 | P1-Z6 | P1-Z7 | P1-Z8 | P1-Z9 | P1 Win/Lose Zone | P2-Z1 | P2-Z2 | P2-Z3 | P2-Z4 | P2-Z5 | P2-Z6 | P2-Z7 | P2-Z8 | P2-Z9 | P2 Win/Lose Zone | Confidence |
|----|-------------|------|----------|----------|-------------|--------|--------|--------|--------|--------|--------|--------|--------|--------|-----------------|--------|--------|--------|--------|--------|--------|--------|--------|--------|-----------------|------------|
| 1 | Player 1 | 1 | 1 | 0 | 6 | 0 | 1 | 0 | 0 | 1 | 0 | 0 | 1 | 0 | 8 | 1 | 0 | 0 | 0 | 1 | 0 | 0 | 0 | 1 | 9 | 0.85 |

Interpretation: During this rally, shots landed in zones 2, 5, 8 on Player 1's court and zones 1, 5, 9 on Player 2's court. The winning shot landed in zone 8 (Player 1's front-center — a net shot winner). The losing shot (Player 2's last shot) landed in zone 9 (Player 2's front-right).

---

## Appendix B — Zone Reference Image

See: `badminton_court_9zone.png`

Zone grid per player's half (from player's perspective facing net):

```
         BASELINE
    ┌───┬───┬───┐
    │ 1 │ 2 │ 3 │  Back
    ├───┼───┼───┤
    │ 4 │ 5 │ 6 │  Mid
    ├───┼───┼───┤
    │ 7 │ 8 │ 9 │  Front
    └───┴───┴───┘
          NET
```

---

## Appendix C — Reference Video Characteristics

Source: BWF World Tour broadcast (e.g., Sydney International)
- Players: Dong T.Y. vs Farhan (Alwi Farhan)
- Camera: Elevated behind baseline, ~30–40° angle
- Scoreboard: Top-left overlay with player names and game score
- Court surface: Green playing area, blue surround
- Court lines: White/yellow, clearly visible

---

## Decision Log

| Date | Decision | Rationale |
|------|----------|-----------|
| 2026-06-16 | Pivot from manual annotation (v1.0) to automated CV pipeline (v2.0) | Manual annotation too slow; automated analysis is the core value proposition |
| 2026-06-16 | Backend-only, no frontend | User only needs input → output; no interactive UI required |
| 2026-06-16 | MP4 only, 100MB / 20min limits | Keep scope manageable; prevents excessively long processing times |
| 2026-06-16 | Zone numbering: Z1–Z3 back, Z7–Z9 front | Matches reference image (badminton_court_9zone.png) |
| 2026-06-16 | Add winning/losing shot zone column | Enables quick identification of where points are won/lost |
| 2026-06-16 | Promote player-name OCR to v1 requirement | User needs output tied to actual players shown in the video |
| 2026-06-16 | Treat scoreboard score changes as mandatory point events | Reference video shows more score progression than first pipeline output captured |
