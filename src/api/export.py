from fastapi import APIRouter

router = APIRouter()


@router.get("/{session_id}/csv")
async def export_csv(session_id: str):
    """Export session data as CSV (one row per shot)."""
    pass


@router.get("/{session_id}/json")
async def export_json(session_id: str):
    """Export full session object as JSON."""
    pass
