from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Optional
from uuid import uuid4

import httpx

from .config import get_settings


CHATKIT_ENDPOINT = "https://api.openai.com/v1/chatkit/sessions"


@dataclass
class ChatKitSession:
    session_id: str
    client_secret: str
    expires_at: Optional[datetime]


class ChatKitService:
    def __init__(self) -> None:
        settings = get_settings()
        self.api_key = settings.openai_api_key
        self.workflow_id = settings.workflow_id

    def _resolve_user_id(self, device_id: Optional[str]) -> str:
        return device_id or str(uuid4())

    def _parse_session(self, data: Dict[str, Any]) -> ChatKitSession:
        expires_at: Optional[datetime] = None
        expiry_value = data.get("expires_at")
        if isinstance(expiry_value, str):
            try:
                expires_at = datetime.fromisoformat(expiry_value.replace("Z", "+00:00"))
            except ValueError:
                expires_at = None
        return ChatKitSession(
            session_id=data.get("id", ""),
            client_secret=data.get("client_secret", ""),
            expires_at=expires_at,
        )

    def create_session(self, device_id: Optional[str], metadata: Optional[Dict[str, Any]] = None) -> ChatKitSession:
        user_id = self._resolve_user_id(device_id)
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "OpenAI-Beta": "chatkit_beta=v1",
        }
        payload = {
            "workflow": {"id": self.workflow_id},
            "user": user_id,
        }
        if metadata:
            payload["metadata"] = metadata
        response = httpx.post(CHATKIT_ENDPOINT, headers=headers, json=payload, timeout=30)
        try:
            response.raise_for_status()
        except httpx.HTTPStatusError as exc:  # pragma: no cover - bubbled to handler
            detail = {
                "status_code": exc.response.status_code,
                "body": exc.response.text,
            }
            raise RuntimeError(detail) from exc
        data: Dict[str, Any] = response.json()
        return self._parse_session(data)
