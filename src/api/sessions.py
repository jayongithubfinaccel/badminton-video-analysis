from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def create_session():
    """Create a new annotation session with match metadata."""
    pass


@router.get("/")
async def list_sessions():
    """List all saved sessions."""
    pass


@router.get("/{session_id}")
async def get_session(session_id: str):
    """Get a specific session by ID."""
    pass


@router.put("/{session_id}")
async def update_session(session_id: str):
    """Update session metadata."""
    pass


@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Delete a session."""
    pass
