from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api import sessions, shots, rallies, analytics, export

app = FastAPI(
    title="Badminton Video Analysis API",
    description="Backend service for shot-by-shot badminton match annotation and analysis",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions.router, prefix="/api/sessions", tags=["sessions"])
app.include_router(shots.router, prefix="/api/shots", tags=["shots"])
app.include_router(rallies.router, prefix="/api/rallies", tags=["rallies"])
app.include_router(analytics.router, prefix="/api/analytics", tags=["analytics"])
app.include_router(export.router, prefix="/api/export", tags=["export"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "badminton-video-analysis"}
