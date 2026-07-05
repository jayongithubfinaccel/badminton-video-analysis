# CLAUDE.md

Guidance for Claude Code when working in this repository.

## Repository

- **GitHub**: https://github.com/jayongithubfinaccel/badminton-video-analysis
- **Owner**: jayfetra (sole contributor — safe to commit and push directly to `main`, no PR review required)
- Standard workflow: commit directly to `main`. Only use a feature branch if the user explicitly asks for one (e.g. for a large/risky change they want to inspect before merging).

## Project Overview

Backend service that analyzes badminton match videos into structured data (shot annotation, rally tracking, court/shuttle tracking, analytics). Python 3.11+, FastAPI, SQLite/SQLAlchemy, OpenCV/Ultralytics(YOLO)/EasyOCR for the video pipeline.

See [README.md](README.md) for project structure and [ARCHITECTURE.md](ARCHITECTURE.md) for the actual pipeline execution path. Docs/PRDs live in `docs/`.

## Deployment & Testing Policy

**Every deployment or non-trivial code change must be tested before being considered done:**

1. **Run the full test suite** (`pytest`) and confirm it passes before marking work complete.
2. **Write unit tests for new/changed functionality.** No feature, bugfix, or pipeline change ships without accompanying tests in `tests/`.
3. **Manually exercise the change** where automated tests can't reach it (e.g. running the pipeline against a sample video, hitting an API endpoint via `/docs`) — don't rely on type-checking or test-passing alone to claim a feature works.
4. **Log every deployment** in [DEPLOYMENT_LOG.md](DEPLOYMENT_LOG.md) — date, what was deployed/changed, test results, and any follow-ups. Create an entry for every meaningful push to `main`, not just formal "releases."

## Standard Development Procedure

- **Before coding**: understand the existing pattern in the relevant module (`src/api`, `src/models`, `src/schemas`, `src/services`, `src/pipeline`, `src/utils`) and follow it rather than introducing a new convention.
- **Lint**: run `ruff check .` before committing (config in `pyproject.toml`).
- **Tests**: `pytest` (config in `pyproject.toml`, `testpaths = ["tests"]`). Add tests alongside the code they cover.
- **Commits**: small, scoped commits with a clear message describing *why*. Don't bundle unrelated changes.
- **Dependencies**: add to `requirements.txt` / `pyproject.toml` `dependencies` — don't install ad hoc without recording it.
- **Docs**: update `README.md`/`ARCHITECTURE.md` when the pipeline or API surface changes; keep `docs/` PRDs as historical record, don't rewrite past PRD versions.
- **No secrets in the repo**: API keys, credentials, or `.env` files must never be committed.
