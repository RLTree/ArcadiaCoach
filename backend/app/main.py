from datetime import datetime
from typing import Any, Dict, Optional

from chatkit.server import StreamingResult
from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from pydantic import BaseModel, Field
from starlette.responses import JSONResponse

from .chatkit import ChatKitService, ChatKitSession
from .chat_server import ArcadiaChatServer, create_chat_server
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
_chat_server: Optional[ArcadiaChatServer] = None


def get_service() -> ChatKitService:
    global _service
    if _service is None:
        _service = ChatKitService()
    return _service


def get_chat_server() -> ArcadiaChatServer:
    global _chat_server
    if _chat_server is None:
        _chat_server = create_chat_server()
    return _chat_server


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


@app.post("/chatkit")
async def chatkit_endpoint(request: Request, server: ArcadiaChatServer = Depends(get_chat_server)) -> Response:
    payload = await request.body()
    result = await server.process(payload, {"request": request})
    if isinstance(result, StreamingResult):
        return StreamingResponse(result, media_type="text/event-stream")
    if hasattr(result, "json"):
        return Response(content=result.json, media_type="application/json")
    return JSONResponse(result)


@app.post("/api/chatkit/upload")
async def upload_chatkit_file(
    file: UploadFile = File(...),
    server: ArcadiaChatServer = Depends(get_chat_server),
) -> Dict[str, Any]:
    return await server.handle_file_upload(file)
