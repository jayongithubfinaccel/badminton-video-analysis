# Copilot Instructions — Badminton Video Analysis Service

## Project Context

This is a **backend-only** Python service for badminton match video annotation and data analysis. No frontend. The service provides REST APIs for recording shot-by-shot annotation data and exporting it for analysis.

## Architecture

- **Framework**: FastAPI (async)
- **Database**: SQLite via SQLAlchemy 2.0 (async)
- **Validation**: Pydantic v2
- **Export**: Pandas (CSV), native JSON
- **Testing**: pytest + httpx

## Key Domain Concepts

- **Session**: A single match annotation (metadata + rallies + shots)
- **Rally**: A sequence of shots ending in a winner or error
- **Shot**: One stroke — who hit it, what type, where it landed, outcome
- **Zone**: 3×3 court grid (1-9) on receiver's half
- **Shot Types**: 23 BWF-classified stroke types

## Coding Conventions

- Python 3.11+ with type hints everywhere
- Async/await for all DB operations
- API → Service → Model separation
- UUID primary keys
- Pydantic for all request/response validation
- ruff for linting (line length 100)
- Tests in `tests/` using pytest-asyncio

## Available Agents

Use `@` to invoke specialized agents:
- **@senior-pm** — PRD updates, requirements, user stories
- **@senior-engineer** — Backend implementation
- **@data-scientist** — Analysis scripts, data quality, methodology
- **@senior-qa** — Testing and quality validation
- **@senior-deployment** — Docker, CI/CD, production readiness
