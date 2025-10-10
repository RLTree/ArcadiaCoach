from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from .chatkit import ChatKitService, ChatKitSession
from .config import Settings, get_settings


class SessionRequest(BaseModel):
    device_id: Optional[str] = Field(default=None, description="Stable identifier for the requesting device/user.")
    metadata: Optional[Dict[str, Any]] = Field(default=None, description="Optional additional metadata for workflow analytics.")


class SessionResponse(BaseModel):
    session_id: str = Field(..., description="ChatKit session identifier.")
    client_secret: str = Field(..., description="Short-lived client secret to hand to ChatKit.")
    expires_at: Optional[datetime] = Field(default=None, description="Expiry timestamp returned by OpenAI.")


app = FastAPI(title="Arcadia Coach Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


_service: Optional[ChatKitService] = None


def get_service() -> ChatKitService:
    global _service
    if _service is None:
        _service = ChatKitService()
    return _service


@app.get("/healthz")
def health(settings: Settings = Depends(get_settings)) -> Dict[str, str]:
    return {"status": "ok", "workflow_id": settings.workflow_id}


@app.post("/api/chatkit/session", response_model=SessionResponse)
def create_session(payload: SessionRequest, service: ChatKitService = Depends(get_service)) -> SessionResponse:
    try:
        session: ChatKitSession = service.create_session(device_id=payload.device_id, metadata=payload.metadata)
    except RuntimeError as exc:
        detail = getattr(exc, "args", [{}])[0] or {}
        raise HTTPException(status_code=502, detail={"message": "ChatKit session creation failed", **detail}) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="Unexpected error creating ChatKit session") from exc
    return SessionResponse(
        session_id=session.session_id,
        client_secret=session.client_secret,
        expires_at=session.expires_at,
    )
