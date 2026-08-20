from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from .models import Channel, DeliveryReceipt, Recipient, XProfile


class XApiError(RuntimeError):
    pass


Transport = Callable[[urllib.request.Request], dict[str, Any]]


def _default_transport(request: urllib.request.Request) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=15) as response:  # noqa: S310
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise XApiError(f"X API returned HTTP {error.code}: {detail}") from error
    except urllib.error.URLError as error:
        raise XApiError(f"Could not reach X API: {error.reason}") from error


class XProfileSearch:
    def __init__(
        self,
        bearer_token: str | None = None,
        transport: Transport = _default_transport,
    ) -> None:
        self._token = bearer_token or os.getenv("X_BEARER_TOKEN", "")
        if not self._token:
            raise ValueError("X_BEARER_TOKEN is required for profile search")
        self._transport = transport

    def search(self, query: str, max_results: int = 10) -> list[XProfile]:
        query = query.strip()
        if not query:
            raise ValueError("Search query cannot be empty")
        if not 1 <= max_results <= 10:
            raise ValueError("Device profile search supports 1 to 10 results")
        params = urllib.parse.urlencode(
            {
                "query": query,
                "max_results": max_results,
                "user.fields": "description,location,profile_image_url,verified",
            }
        )
        request = urllib.request.Request(
            f"https://api.x.com/2/users/search?{params}",
            headers={"Authorization": f"Bearer {self._token}"},
        )
        payload = self._transport(request)
        if payload.get("errors") and not payload.get("data"):
            raise XApiError(json.dumps(payload["errors"], ensure_ascii=False))
        return [XProfile.model_validate(item) for item in payload.get("data", [])][:max_results]


class XDirectMessageSender:
    channel = Channel.X

    def __init__(
        self,
        user_access_token: str | None = None,
        transport: Transport = _default_transport,
    ) -> None:
        self._token = user_access_token or os.getenv("X_USER_ACCESS_TOKEN", "")
        if not self._token:
            raise ValueError("X_USER_ACCESS_TOKEN is required for direct messages")
        self._transport = transport

    def send(self, recipient: Recipient, body: str) -> DeliveryReceipt:
        if not recipient.identifier.isdigit():
            raise ValueError("X delivery requires the recipient's numeric user ID")
        if not body.strip():
            raise ValueError("Cannot send an empty direct message")
        data = json.dumps({"text": body}, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            "https://api.x.com/2/dm_conversations/with/"
            f"{urllib.parse.quote(recipient.identifier, safe='')}/messages",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
        )
        payload = self._transport(request)
        result = payload.get("data") or {}
        message_id = result.get("dm_event_id")
        if not message_id:
            raise XApiError(f"X API response did not include a DM event ID: {payload}")
        return DeliveryReceipt(
            channel=Channel.X,
            recipient_id=recipient.identifier,
            provider_message_id=str(message_id),
            status="sent",
        )
