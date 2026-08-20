from __future__ import annotations

import hashlib
import json
import secrets
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .models import Channel, DeliveryReceipt, Recipient


class Sender(Protocol):
    channel: Channel

    def send(self, recipient: Recipient, body: str) -> DeliveryReceipt: ...


class ConfirmationError(RuntimeError):
    pass


@dataclass
class _Approval:
    digest: str
    expires_at: float
    used: bool = False


class ConfirmationTokens:
    """Issues short-lived tokens bound to the exact channel, recipient, and body."""

    def __init__(
        self,
        ttl_seconds: float = 300,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ttl = ttl_seconds
        self._clock = clock
        self._tokens: dict[str, _Approval] = {}
        self._lock = threading.Lock()

    @staticmethod
    def message_digest(channel: Channel, recipient: Recipient, body: str) -> str:
        payload = json.dumps(
            {"channel": channel.value, "recipient": recipient.identifier, "body": body},
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def issue(self, channel: Channel, recipient: Recipient, body: str) -> str:
        token = secrets.token_urlsafe(32)
        approval = _Approval(
            digest=self.message_digest(channel, recipient, body),
            expires_at=self._clock() + self._ttl,
        )
        with self._lock:
            self._tokens[token] = approval
        return token

    def consume(self, token: str, channel: Channel, recipient: Recipient, body: str) -> None:
        digest = self.message_digest(channel, recipient, body)
        with self._lock:
            approval = self._tokens.get(token)
            if approval is None:
                raise ConfirmationError("Unknown confirmation token")
            if approval.used:
                raise ConfirmationError("Confirmation token has already been used")
            if self._clock() > approval.expires_at:
                raise ConfirmationError("Confirmation token has expired")
            if not secrets.compare_digest(approval.digest, digest):
                raise ConfirmationError("Recipient or message changed after confirmation")
            approval.used = True


class ConfirmedDelivery:
    def __init__(
        self,
        senders: dict[Channel, Sender],
        tokens: ConfirmationTokens | None = None,
    ) -> None:
        self._senders = senders
        self.tokens = tokens or ConfirmationTokens()

    def prepare(self, channel: Channel, recipient: Recipient, body: str) -> str:
        if channel not in self._senders:
            raise ValueError(f"No sender configured for channel: {channel.value}")
        if not body.strip():
            raise ValueError("Cannot send an empty message")
        return self.tokens.issue(channel, recipient, body)

    def deliver(
        self,
        token: str,
        channel: Channel,
        recipient: Recipient,
        body: str,
    ) -> DeliveryReceipt:
        self.tokens.consume(token, channel, recipient, body)
        return self._senders[channel].send(recipient, body)


class OutboxSender:
    """Safe development sender that appends messages to a local JSONL file."""

    def __init__(self, path: Path, channel: Channel = Channel.OTHER) -> None:
        self.path = path
        self.channel = channel

    def send(self, recipient: Recipient, body: str) -> DeliveryReceipt:
        message_id = str(uuid.uuid4())
        record = {
            "message_id": message_id,
            "channel": self.channel.value,
            "recipient_id": recipient.identifier,
            "recipient_name": recipient.display_name,
            "body": body,
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(record, ensure_ascii=False) + "\n")
        return DeliveryReceipt(
            channel=self.channel,
            recipient_id=recipient.identifier,
            provider_message_id=message_id,
            status="queued",
        )
