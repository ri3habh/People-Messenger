from __future__ import annotations

import time
from collections.abc import Callable
from enum import StrEnum

from .ai import MessageGenerator
from .delivery import ConfirmedDelivery
from .models import ComposeDecision, DeliveryReceipt, Draft, MessageContext, StyleProfile


class DeviceState(StrEnum):
    HOME = "home"
    RECORDING_RECIPIENT = "recording_recipient"
    SELECTING_PROFILE = "selecting_profile"
    RECORDING_MESSAGE = "recording_message"
    NEEDS_CONTEXT = "needs_context"
    REVIEWING_DRAFTS = "reviewing_drafts"
    REFINING = "refining"
    CONFIRMING = "confirming"
    SENDING = "sending"
    SENT = "sent"
    REFUSED = "refused"
    ERROR = "error"


class InvalidTransition(RuntimeError):
    pass


class MessengerWorkflow:
    MIN_SEND_HOLD_SECONDS = 2.0

    def __init__(
        self,
        generator: MessageGenerator,
        delivery: ConfirmedDelivery,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.generator = generator
        self.delivery = delivery
        self.clock = clock
        self.state = DeviceState.HOME
        self.profile: StyleProfile | None = None
        self.context: MessageContext | None = None
        self.decision: ComposeDecision | None = None
        self.selected_draft: Draft | None = None
        self.last_error: str | None = None
        self._confirmation_token: str | None = None
        self._send_pressed_at: float | None = None

    def begin_recipient_recording(self) -> None:
        self._require(DeviceState.HOME)
        self.state = DeviceState.RECORDING_RECIPIENT

    def show_profiles(self) -> None:
        self._require(DeviceState.RECORDING_RECIPIENT)
        self.state = DeviceState.SELECTING_PROFILE

    def select_profile(self) -> None:
        self._require(DeviceState.SELECTING_PROFILE)
        self.state = DeviceState.RECORDING_MESSAGE

    def compose(
        self,
        samples: list[str],
        context: MessageContext,
        profile: StyleProfile | None = None,
    ) -> ComposeDecision:
        allowed = {DeviceState.HOME, DeviceState.RECORDING_MESSAGE, DeviceState.NEEDS_CONTEXT}
        if self.state not in allowed:
            raise InvalidTransition(f"Cannot compose from {self.state.value}")
        self.profile = profile or self.generator.learn_voice(samples)
        self.context = context
        self.decision = self.generator.compose(self.profile, context)
        self.selected_draft = None
        self._invalidate_confirmation()
        if self.decision.status == "ready":
            self.state = DeviceState.REVIEWING_DRAFTS
        elif self.decision.status == "needs_context":
            self.state = DeviceState.NEEDS_CONTEXT
        else:
            self.state = DeviceState.REFUSED
        return self.decision

    def answer_context(self, answers: list[str]) -> ComposeDecision:
        self._require(DeviceState.NEEDS_CONTEXT)
        if not self.context or not self.profile:
            raise InvalidTransition("No active composition")
        if not self.decision or self.decision.status != "needs_context":
            raise InvalidTransition("No context questions are available")
        if len(answers) != len(self.decision.questions):
            raise ValueError("Provide one answer for each context question")
        question_answers = [
            f"Question: {question}\nAnswer: {answer.strip()}"
            for question, answer in zip(self.decision.questions, answers, strict=True)
            if answer.strip()
        ]
        if not question_answers:
            raise ValueError("At least one context answer is required")
        updated = self.context.model_copy(
            update={"additional_context": [*self.context.additional_context, *question_answers]}
        )
        return self.compose([], updated, profile=self.profile)

    def choose_draft(self, index: int) -> Draft:
        self._require(DeviceState.REVIEWING_DRAFTS)
        if not self.decision or self.decision.status != "ready":
            raise InvalidTransition("No drafts are available")
        try:
            self.selected_draft = self.decision.drafts[index]
        except IndexError as error:
            raise ValueError("Draft index is out of range") from error
        return self.selected_draft

    def begin_refinement(self) -> None:
        self._require(DeviceState.REVIEWING_DRAFTS)
        if not self.selected_draft:
            raise InvalidTransition("Choose a draft before refining it")
        self._invalidate_confirmation()
        self.state = DeviceState.REFINING

    def refine(self, instruction: str) -> Draft:
        self._require(DeviceState.REFINING)
        if not self.profile or not self.context or not self.selected_draft:
            raise InvalidTransition("No selected draft to refine")
        self.selected_draft = self.generator.refine(
            self.profile, self.context, self.selected_draft, instruction
        )
        self.state = DeviceState.REVIEWING_DRAFTS
        return self.selected_draft

    def show_final_confirmation(self) -> str:
        self._require(DeviceState.REVIEWING_DRAFTS)
        if not self.context or not self.selected_draft:
            raise InvalidTransition("Choose a draft before confirmation")
        self._confirmation_token = self.delivery.prepare(
            self.context.channel, self.context.recipient, self.selected_draft.body
        )
        self.state = DeviceState.CONFIRMING
        return self._confirmation_token

    def press_send(self) -> None:
        self._require(DeviceState.CONFIRMING)
        if self._send_pressed_at is not None:
            raise InvalidTransition("SEND is already pressed")
        self._send_pressed_at = self.clock()

    def release_send(self) -> DeliveryReceipt | None:
        self._require(DeviceState.CONFIRMING)
        if self._send_pressed_at is None:
            raise InvalidTransition("SEND was not pressed")
        held_for = self.clock() - self._send_pressed_at
        self._send_pressed_at = None
        if held_for < self.MIN_SEND_HOLD_SECONDS:
            return None
        if not self.context or not self.selected_draft or not self._confirmation_token:
            raise InvalidTransition("Confirmation data is incomplete")
        self.state = DeviceState.SENDING
        try:
            receipt = self.delivery.deliver(
                self._confirmation_token,
                self.context.channel,
                self.context.recipient,
                self.selected_draft.body,
            )
        except Exception as error:
            self.last_error = str(error)
            self.state = DeviceState.ERROR
            raise
        self._confirmation_token = None
        self.last_error = None
        self.state = DeviceState.SENT
        return receipt

    def back_from_confirmation(self) -> None:
        self._require(DeviceState.CONFIRMING)
        self._invalidate_confirmation()
        self.state = DeviceState.REVIEWING_DRAFTS

    def _invalidate_confirmation(self) -> None:
        self._confirmation_token = None
        self._send_pressed_at = None

    def _require(self, expected: DeviceState) -> None:
        if self.state != expected:
            raise InvalidTransition(f"Expected {expected.value}, got {self.state.value}")
