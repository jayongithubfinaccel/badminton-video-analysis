# Badminton Video Analysis — Backend Service

A backend service for analyzing badminton match videos into structured data. Supports shot-by-shot annotation, data collection, and analysis for singles matches.

## Overview

This service provides APIs for:
- **Session Management** — Create, load, save, and manage annotation sessions
- **Shot Annotation** — Record shot-by-shot data (player, shot type, landing zone, outcome)
- **Rally Tracking** — Organize shots into rallies with start/end markers
- **Data Export** — Export annotation data as CSV and JSON
- **Analytics** — Shot frequency, zone heatmaps, per-rally statistics

## Tech Stack

- **Python 3.11+**
- **FastAPI** — async REST API framework
- **SQLite** — local database (no external DB required)
- **SQLAlchemy** — ORM for data models
- **Pydantic** — request/response validation
- **Pandas** — data analysis and export

## Project Structure

```
badminton-video-analysis/
├── .github/
│   ├── agents/          # Custom Copilot agents for development workflow
│   └── copilot-instructions.md
├── src/
│   ├── api/             # FastAPI route handlers
│   ├── models/          # SQLAlchemy models
│   ├── schemas/         # Pydantic schemas
│   ├── services/        # Business logic
│   ├── utils/           # Helpers (export, shot types, etc.)
│   └── main.py          # App entrypoint
├── tests/               # Test suite
├── data/                # Sample data and exports
├── docs/                # PRD and documentation
├── requirements.txt
├── pyproject.toml
└── README.md
```

## Quick Start

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows

# Install dependencies
pip install -r requirements.txt

# Run the service
uvicorn src.main:app --reload --port 8000
```

API docs available at `http://localhost:8000/docs`

## Data Model

Each session contains:
- **Match metadata** — tournament, date, players
- **Rallies** — sequential rally segments
- **Shots** — per-shot records with timestamp, player, shot type, zone, outcome

### Shot Type Taxonomy (23 types from BWF)

See `src/utils/shot_types.py` for the full list.

### Court Zones (3×3 grid)

```
Row 1 (Net):  Z1 Left · Z2 Center · Z3 Right
Row 2 (Mid):  Z4 Left · Z5 Center · Z6 Right
Row 3 (Back): Z7 Left · Z8 Center · Z9 Right
```

## License

MIT
