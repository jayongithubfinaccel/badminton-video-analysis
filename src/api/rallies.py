from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def start_rally():
    """Start a new rally in a session."""
    pass


@router.put("/{rally_id}/end")
async def end_rally(rally_id: str):
    """End a rally with winner/error outcome."""
    pass


@router.get("/{session_id}")
async def list_rallies(session_id: str):
    """List all rallies in a session."""
    pass
