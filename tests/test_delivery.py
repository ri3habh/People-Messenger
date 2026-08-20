from __future__ import annotations

from dataclasses import dataclass

import pytest

from people_messenger.delivery import ConfirmationError, ConfirmationTokens, ConfirmedDelivery
from people_messenger.models import Channel, DeliveryReceipt, Recipient


@dataclass
class FakeSender:
    channel: Channel = Channel.X
    calls: int = 0

    def send(self, recipient: Recipient, body: str) -> DeliveryReceipt:
        self.calls += 1
        return DeliveryReceipt(
            channel=self.channel,
            recipient_id=recipient.identifier,
            provider_message_id="dm-1",
            status="sent",
        )


def test_confirmation_is_bound_to_exact_message() -> None:
    sender = FakeSender()
    recipient = Recipient(identifier="123", display_name="Sam")
    delivery = ConfirmedDelivery({Channel.X: sender})
    token = delivery.prepare(Channel.X, recipient, "Hello")

    with pytest.raises(ConfirmationError, match="changed"):
        delivery.deliver(token, Channel.X, recipient, "Hello!")
    assert sender.calls == 0


def test_confirmation_token_is_one_time() -> None:
    sender = FakeSender()
    recipient = Recipient(identifier="123", display_name="Sam")
    delivery = ConfirmedDelivery({Channel.X: sender})
    token = delivery.prepare(Channel.X, recipient, "Hello")

    delivery.deliver(token, Channel.X, recipient, "Hello")
    with pytest.raises(ConfirmationError, match="already"):
        delivery.deliver(token, Channel.X, recipient, "Hello")
    assert sender.calls == 1


def test_confirmation_expires() -> None:
    now = [10.0]
    tokens = ConfirmationTokens(ttl_seconds=5, clock=lambda: now[0])
    sender = FakeSender()
    recipient = Recipient(identifier="123", display_name="Sam")
    delivery = ConfirmedDelivery({Channel.X: sender}, tokens)
    token = delivery.prepare(Channel.X, recipient, "Hello")
    now[0] = 16.0

    with pytest.raises(ConfirmationError, match="expired"):
        delivery.deliver(token, Channel.X, recipient, "Hello")
