# Badminton Video Analysis App — PRD v1.0

> **Version:** 1.0 — Initial Release  
> **Status:** Draft  
> **Author:** Jayson Fetra  
> **Date:** 15 June 2026  
> **Platform:** Web App (browser-based, local storage)

---

## 1. Overview

This app lets a user — player, coach, or analyst — watch a badminton match video and manually tag each shot in real time or during review. For every shot, the user records which player hit it, what type of shot it was, and where the shuttle landed using a 9-zone court grid. All data is saved locally to the device and can be exported as JSON or CSV for further analysis.

The initial scope covers singles matches. The core output is a per-rally shot log that can feed downstream analysis including win prediction modelling, zone heatmaps, and shot-type frequency breakdown — consistent with the methodology used in the 2025 Scientific Reports study on badminton outcome prediction (Sheng et al.).

---

## 2. Problem Statement

Automated badminton video analysis (shuttle tracking, pose estimation, shot classification) requires significant engineering infrastructure and custom-trained CV models. For a solo analyst or small coaching team, the practical near-term path to structured match data is manual annotation — but no lightweight, purpose-built tool exists for this workflow.

Existing options are either too generic (spreadsheets, generic video taggers) or too expensive and complex (Dartfish, Nacsport). The goal is a fast, purpose-built browser app that requires no backend, no login, and no internet connection during use.

---

## 3. Goals and Non-Goals

### 3.1 Goals

- Enable shot-by-shot manual annotation of a badminton match video
- Map each shot to one of 9 court zones on the receiver's half
- Record shot type per the 23-category taxonomy from BWF/research literature
- Save session data locally (localStorage / IndexedDB) — no backend required
- Export data as CSV and JSON for use in Python/Excel analysis
- Display live heatmaps and shot-type frequency during annotation
- Support multiple rallies and multiple matches in one session

### 3.2 Non-Goals (v1)

- Automated shuttle or player tracking (no CV/ML in v1)
- User accounts, cloud sync, or multi-device collaboration
- Doubles match support
- Video upload or transcoding — user loads video from their local file system
- Mobile-native app — desktop browser only in v1

---

## 4. User Stories

| ID | User Story |
|----|-----------|
| US-01 | As a coach, I want to load a match video from my computer and annotate each shot without leaving the browser. |
| US-02 | As an analyst, I want to assign each shot to one of 9 court zones on the receiver's half, to build heatmaps. |
| US-03 | As a user, I want to tag the shot type and hitting player for each shot, to measure shot-type frequency. |
| US-04 | As a user, I want keyboard shortcuts to tag shots quickly while the video plays. |
| US-05 | As an analyst, I want a live heatmap and shot-type chart updating as I annotate. |
| US-06 | As a user, I want to export annotation data as CSV and JSON. |
| US-07 | As a user, I want to save my session and resume it later. |
| US-08 | As a user, I want to edit or delete a previously tagged shot. |
| US-09 | As a user, I want to define player names at session start. |
| US-10 | As a user, I want to mark rally start/end for per-rally statistics. |

---

## 5. Feature Specifications

### 5.1 Session Setup

- User enters match metadata: tournament name, date, Player A name, Player B name
- User selects which player starts at the bottom of the court view
- User loads video file from local disk via file picker (no upload to server)
- Session auto-saves to localStorage on every shot tagged

### 5.2 Video Player

- Standard HTML5 video player with play/pause, seek bar, and speed control (0.5×, 0.75×, 1×, 1.5×, 2×)
- Frame-by-frame step buttons (+1 frame, -1 frame) for precise moment capture
- Spacebar to play/pause; current timestamp displayed as MM:SS.ms
- Video occupies left 60% of screen; annotation panel on the right 40%

### 5.3 Court Zone Picker

- Visual 3×3 grid representing the receiver's half of the court
- Zones numbered 1–9: left-to-right, near-to-far from the receiver's perspective
  - Row 1 (Net):  Z1 Left · Z2 Center · Z3 Right
  - Row 2 (Mid):  Z4 Left · Z5 Center · Z6 Right
  - Row 3 (Back): Z7 Left · Z8 Center · Z9 Right
- Keyboard: numpad 1–9 maps directly to zones 1–9
- Separate zone pickers shown for each player's half

### 5.4 Shot Annotation Panel

| Field | Details |
|-------|---------|
| Timestamp | Auto-captured from video at moment of tagging. Editable. |
| Rally number | Auto-incremented. Press R to start new rally. |
| Hitting player | Toggle A / B. Keyboard: A or B key. |
| Shot type | Dropdown: 23 types (see Appendix A). Common types mapped to keys. |
| Landing zone | Selected via court zone picker. Zones 1–9. |
| Outcome | Winner / Error / In Play. Auto 'In Play'; user marks end of rally. |
| Notes | Optional free-text observation field. |

> Pressing Enter commits the annotation. Panel resets immediately, inheriting the last hitter and flipping it.

### 5.5 Shot Log Table

- Scrollable table: #, Time, Rally, Player, Shot Type, Zone, Outcome, Notes
- Each row has Edit and Delete buttons
- Click any row to seek video to that timestamp
- Rows color-coded by player

### 5.6 Live Analytics Panel

- Court heatmap: two 3×3 grids showing shot frequency per zone; intensity scales with count
- Shot-type bar chart: frequency by shot type, split by player, updates in real time
- Summary stats: total shots, avg shots per rally, rally count, win rate per player
- Toggle between "All rallies" and "Current rally" view

### 5.7 Data Persistence and Export

- Auto-save to localStorage after every shot tag
- "Save Session" writes JSON to IndexedDB for large datasets
- "Load Session" restores a previously saved session
- Export: CSV (one row per shot) and JSON (full session object)
- Session manager: list, rename, delete saved sessions

---

## 6. Technical Architecture

### 6.1 Technology Stack

| Layer | Choice & Rationale |
|-------|-------------------|
| Framework | React (Vite) — component-based, fast local dev, no backend needed |
| Styling | Tailwind CSS — utility-first, responsive layout |
| State management | React Context + useReducer |
| Storage | localStorage (metadata) + IndexedDB via idb-keyval (shot data) |
| Charts | Recharts — React-native, no canvas sizing issues |
| Video | Native HTML5 `<video>` element — works offline |
| Export | PapaParse (CSV) + native JSON.stringify |
| Build | Vite — instant HMR, simple config |

### 6.2 Folder Structure

```
badminton-analyzer/
├── public/
├── src/
│   ├── components/
│   │   ├── VideoPlayer.jsx
│   │   ├── CourtZonePicker.jsx
│   │   ├── ShotAnnotationPanel.jsx
│   │   ├── ShotLogTable.jsx
│   │   ├── AnalyticsPanel.jsx
│   │   ├── SessionSetup.jsx
│   │   └── ExportControls.jsx
│   ├── context/
│   │   └── SessionContext.jsx
│   ├── hooks/
│   │   ├── useKeyboardShortcuts.js
│   │   └── useLocalStorage.js
│   ├── utils/
│   │   ├── exportCsv.js
│   │   └── shotTypes.js
│   ├── App.jsx
│   └── main.jsx
├── tailwind.config.js
├── vite.config.js
└── package.json
```

### 6.3 Data Model

```json
{
  "id": "uuid",
  "tournament": "Australian Open 2026",
  "date": "2026-06-15",
  "playerA": { "name": "Alwi Farhan", "country": "ID", "courtSide": "bottom" },
  "playerB": { "name": "Dong",        "country": "CN", "courtSide": "top"    },
  "createdAt": "ISO timestamp",
  "rallies": [
    {
      "rallyNumber": 1,
      "startTime":   22.0,
      "endTime":     42.3,
      "winner":      "playerA",
      "shots": [
        {
          "id":            "uuid",
          "rallyNumber":   1,
          "shotNumber":    1,
          "timestamp":     22.4,
          "hittingPlayer": "playerA",
          "shotType":      "High serve",
          "landingZone":   8,
          "outcome":       "in_play",
          "notes":         ""
        }
      ]
    }
  ]
}
```

---

## 7. UX and Interaction Design

### 7.1 Layout

- Two-column: video player (left 60%) + annotation panel (right 40%)
- Analytics panel below, toggled via tabs: "Live Stats" | "Shot Log"
- Full-width header: match title, running score, session controls
- Designed for 1440px+ desktop — not optimized for mobile in v1

### 7.2 Keyboard Shortcut Map

| Key | Action |
|-----|--------|
| Space | Play / Pause video |
| ← / → | Seek −5s / +5s |
| , / . | Step back / forward one frame |
| A / B | Select Player A / Player B as hitter |
| 1–9 (numpad) | Select landing zone 1–9 |
| Enter | Commit shot annotation |
| R | Mark new rally start |
| W | Mark rally winner = current hitter |
| E | Mark rally as error by current hitter |
| Escape | Cancel annotation in progress |
| Ctrl+Z | Undo last tagged shot |

### 7.3 Annotation Workflow

1. Load session or start new — enter match metadata and player names
2. Load video file from local disk
3. Press R to start Rally 1 and begin playback
4. When a shot is made: pause (Space), select player (A/B), select shot type, select zone (numpad), press Enter
5. Continue for next shot; video auto-resumes if toggle is on
6. When rally ends: press W (winner) or E (error) to close the rally
7. Press R to start the next rally
8. Export data at any time via the Export panel

---

## 8. Acceptance Criteria

| ID | Criterion |
|----|-----------|
| AC-01 | User can load .mp4 or .mov from local disk and play it without page reload. |
| AC-02 | All 23 shot types from Appendix A are available in the shot type selector. |
| AC-03 | Selecting zone 1–9 via numpad correctly highlights the corresponding court grid cell. |
| AC-04 | Tagged shot appears in the shot log immediately after Enter is pressed. |
| AC-05 | Clicking a shot log row seeks the video to within 0.2s of the tagged timestamp. |
| AC-06 | Court heatmap updates after each shot tag without page refresh. |
| AC-07 | CSV export has one row per shot with all fields; opens correctly in Excel. |
| AC-08 | JSON export matches the data model in section 6.3. |
| AC-09 | Closing and reopening the browser tab restores the session from localStorage. |
| AC-10 | Edit and delete on shot log rows update all derived stats correctly. |
| AC-11 | App functions fully offline after initial page load. |

---

## 9. Milestones and Phasing

| Phase | Scope |
|-------|-------|
| Phase 1 — Core (Week 1–2) | Session setup, video player, court zone picker, shot annotation panel, shot log table, localStorage auto-save |
| Phase 2 — Analytics (Week 3) | Live heatmap, shot-type chart, summary stats, rally segmentation, undo/redo |
| Phase 3 — Export (Week 4) | CSV/JSON export, IndexedDB multi-session management, keyboard shortcut help modal, layout polish |
| Phase 4 — Future | Automated shuttle detection (TrackNet integration), multi-match comparison, cloud sync (optional) |

---

## 10. Open Questions

- Should auto-play resume after each shot tag, or require manual play? (Proposed: user preference toggle)
- Should the app support marking let / service fault as separate outcomes?
- Is a set tracker needed in v1, or is flat rally numbering sufficient?
- Max session size before IndexedDB becomes a bottleneck? (Estimate: 500 shots ≈ ~100KB — fine)

---

## Appendix A — Shot Type Taxonomy

23 technical actions from the BWF taxonomy, consistent with Sheng et al. (Scientific Reports, 2025):

| No. | Shot Type |
|-----|-----------|
| 1 | High (overhead clear to deep baseline) |
| 2 | Smash |
| 3 | Dribble (tight net return) |
| 4 | Push (mid-court push drive) |
| 5 | Slice / Drop |
| 6 | Lift (defensive lift from net area) |
| 7 | Block smash |
| 8 | Net front |
| 9 | Clear |
| 10 | Net drop from lift |
| 11 | Lift from slice |
| 12 | Pull |
| 13 | Hook |
| 14 | Slice lift |
| 15 | Block |
| 16 | Lift smash |
| 17 | Block hook |
| 18 | Hook from lift |
| 19 | Drive |
| 20 | Net drop from slice drive |
| 21 | Lift from slice drive |
| 22 | Flat high |
| 23 | Block from slice drive |

---

## Appendix B — VS Code + GitHub Copilot Setup Guide

### Step 1 — Scaffold the project

```bash
npm create vite@latest badminton-analyzer -- --template react
cd badminton-analyzer && npm install
```

### Step 2 — Install dependencies

```bash
npm install tailwindcss @tailwindcss/vite recharts papaparse idb-keyval uuid
```

### Step 3 — Open Copilot Chat and prompt component by component

Open Copilot Chat (Ctrl+Shift+I) and use prompts like these, one at a time:

- **CourtZonePicker:** "Create a React component CourtZonePicker that renders a 3×3 grid of clickable zones numbered 1–9. Accept onZoneSelect prop and highlight the selected zone. Use Tailwind CSS."
- **SessionContext:** "Create a SessionContext using React Context and useReducer. State: sessionMeta, rallies, currentRally, shots. Actions: ADD_SHOT, DELETE_SHOT, EDIT_SHOT, NEW_RALLY, END_RALLY."
- **VideoPlayer:** "Create a VideoPlayer component wrapping HTML5 video with a local file picker. Expose getCurrentTime() and seekTo(time) via a forwarded ref. Include playback speed control."
- **Export utility:** "Create an exportToCsv utility that takes a shots array and downloads it as a .csv file using PapaParse. Include all fields from the shot data model."

### Step 4 — Run locally

```bash
npm run dev
```

App runs at `http://localhost:5173` — no backend, no accounts, no internet required after first load.

### Step 5 — Build for offline distribution

```bash
npm run build
```

Output goes to `dist/`. Open `dist/index.html` directly in any browser. No deployment infrastructure needed.
