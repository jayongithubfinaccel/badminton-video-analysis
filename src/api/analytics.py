from fastapi import APIRouter

router = APIRouter()


@router.get("/{session_id}/heatmap")
async def get_zone_heatmap(session_id: str):
    """Get shot frequency per zone (3x3 grid) for each player."""
    pass


@router.get("/{session_id}/shot-types")
async def get_shot_type_frequency(session_id: str):
    """Get shot type frequency breakdown by player."""
    pass


@router.get("/{session_id}/summary")
async def get_session_summary(session_id: str):
    """Get summary stats: total shots, avg shots per rally, rally count, win rate."""
    pass
