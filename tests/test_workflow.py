from __future__ import annotations

from dataclasses import dataclass

import pytest

from people_messenger.delivery import ConfirmedDelivery
from people_messenger.models import Channel, ComposeDecision, DeliveryReceipt, Draft
from people_messenger.workflow import DeviceState, InvalidTransition, MessengerWorkflow


class FakeGenerator:
    def __init__(self, profile, decisions) -> None:
        self.profile = profile
        self.decisions = list(decisions)

    def learn_voice(self, samples):
        assert len(samples) >= 2
        return self.profile

    def compose(self, profile, context):
        return self.decisions.pop(0)

    def refine(self, profile, context, draft, instruction):
        return Draft(label=draft.label, body=f"{draft.body} ({instruction})")


@dataclass
class FakeSender:
    channel: Channel = Channel.X
    calls: int = 0

    def send(self, recipient, body):
        self.calls += 1
        return DeliveryReceipt(
            channel=self.channel,
            recipient_id=recipient.identifier,
            provider_message_id="sent-1",
            status="sent",
        )


@dataclass
class FailingSender:
    channel: Channel = Channel.X

    def send(self, recipient, body):
        raise RuntimeError("network outcome is unknown")


def ready_decision() -> ComposeDecision:
    return ComposeDecision(
        status="ready",
        drafts=[
            Draft(label="brief", body="Brief message"),
            Draft(label="warm", body="Warm message"),
            Draft(label="formal", body="Formal message"),
        ],
    )


def test_context_question_then_drafts(style_profile, message_context) -> None:
    generator = FakeGenerator(
        style_profile,
        [
            ComposeDecision(status="needs_context", questions=["When did you meet?"]),
            ready_decision(),
        ],
    )
    sender = FakeSender()
    workflow = MessengerWorkflow(generator, ConfirmedDelivery({Channel.X: sender}))

    decision = workflow.compose(["sample one", "sample two"], message_context)
    assert decision.status == "needs_context"
    assert workflow.state == DeviceState.NEEDS_CONTEXT

    decision = workflow.answer_context(["Today"])
    assert decision.status == "ready"
    assert workflow.context.additional_context == ["Question: When did you meet?\nAnswer: Today"]
    assert workflow.state == DeviceState.REVIEWING_DRAFTS


def test_short_press_never_sends_and_long_hold_sends(style_profile, message_context) -> None:
    now = [100.0]
    sender = FakeSender()
    workflow = MessengerWorkflow(
        FakeGenerator(style_profile, [ready_decision()]),
        ConfirmedDelivery({Channel.X: sender}),
        clock=lambda: now[0],
    )
    workflow.compose(["sample one", "sample two"], message_context)
    workflow.choose_draft(0)
    workflow.show_final_confirmation()

    workflow.press_send()
    now[0] += 0.5
    assert workflow.release_send() is None
    assert sender.calls == 0
    assert workflow.state == DeviceState.CONFIRMING

    workflow.press_send()
    now[0] += 2.1
    receipt = workflow.release_send()
    assert receipt and receipt.provider_message_id == "sent-1"
    assert sender.calls == 1
    assert workflow.state == DeviceState.SENT


def test_refinement_invalidates_confirmation(style_profile, message_context) -> None:
    workflow = MessengerWorkflow(
        FakeGenerator(style_profile, [ready_decision()]),
        ConfirmedDelivery({Channel.X: FakeSender()}),
    )
    workflow.compose(["sample one", "sample two"], message_context)
    workflow.choose_draft(1)
    workflow.show_final_confirmation()
    workflow.back_from_confirmation()
    workflow.begin_refinement()
    draft = workflow.refine("make it shorter")

    assert "make it shorter" in draft.body
    with pytest.raises(InvalidTransition):
        workflow.press_send()


def test_delivery_failure_enters_error_state(style_profile, message_context) -> None:
    now = [10.0]
    workflow = MessengerWorkflow(
        FakeGenerator(style_profile, [ready_decision()]),
        ConfirmedDelivery({Channel.X: FailingSender()}),
        clock=lambda: now[0],
    )
    workflow.compose(["sample one", "sample two"], message_context)
    workflow.choose_draft(0)
    workflow.show_final_confirmation()
    workflow.press_send()
    now[0] += 2.1

    with pytest.raises(RuntimeError, match="unknown"):
        workflow.release_send()
    assert workflow.state == DeviceState.ERROR
    assert workflow.last_error == "network outcome is unknown"
