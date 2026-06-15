from fastapi import APIRouter

router = APIRouter()


@router.post("/")
async def create_shot():
    """Record a new shot annotation."""
    pass


@router.get("/{session_id}")
async def list_shots(session_id: str):
    """List all shots in a session."""
    pass


@router.put("/{shot_id}")
async def update_shot(shot_id: str):
    """Edit an existing shot annotation."""
    pass


@router.delete("/{shot_id}")
async def delete_shot(shot_id: str):
    """Delete a shot annotation."""
    pass
