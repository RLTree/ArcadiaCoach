import logging
from typing import Any, Dict, Optional

from chatkit.server import StreamingResult
from fastapi import Depends, FastAPI, File, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response, StreamingResponse
from starlette.responses import JSONResponse

from .chat_server import ArcadiaChatServer, create_chat_server
from .config import Settings, get_settings
from .logging_config import configure_logging


configure_logging()
logger = logging.getLogger(__name__)
app = FastAPI(title="Arcadia Coach Backend", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

settings_snapshot = get_settings()
logger.info("Backend starting with MCP URL: %s", settings_snapshot.arcadia_mcp_url)
logger.info("OpenAI API key configured: %s", bool(settings_snapshot.openai_api_key))


_chat_server: Optional[ArcadiaChatServer] = None


def get_chat_server() -> ArcadiaChatServer:
    global _chat_server
    if _chat_server is None:
        _chat_server = create_chat_server()
    return _chat_server


@app.get("/healthz")
def health(settings: Settings = Depends(get_settings)) -> Dict[str, str]:
    return {"status": "ok", "mode": "custom-chatkit"}


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
