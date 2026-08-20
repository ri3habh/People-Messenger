from __future__ import annotations

from types import SimpleNamespace

import pytest

from people_messenger.ai import OpenAIMessageGenerator
from people_messenger.models import ComposeDecision, Draft, StyleProfile


class FakeResponses:
    def __init__(self, outputs: list[object]) -> None:
        self.outputs = outputs
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(output_parsed=self.outputs.pop(0))


def test_learn_voice_requires_two_samples() -> None:
    generator = OpenAIMessageGenerator(client=SimpleNamespace(responses=FakeResponses([])))
    with pytest.raises(ValueError, match="two"):
        generator.learn_voice(["Only one sample"])


def test_compose_uses_structured_output(style_profile, message_context) -> None:
    expected = ComposeDecision(
        status="ready",
        drafts=[
            Draft(label="brief", body="Thanks for today, John."),
            Draft(label="warm", body="Thanks again for today, John. I really enjoyed our chat."),
            Draft(label="formal", body="Thank you for your time today, John."),
        ],
    )
    responses = FakeResponses([expected])
    generator = OpenAIMessageGenerator(
        client=SimpleNamespace(responses=responses), model="test-model"
    )

    actual = generator.compose(style_profile, message_context)

    assert actual == expected
    assert responses.calls[0]["model"] == "test-model"
    assert responses.calls[0]["text_format"] is ComposeDecision


def test_compose_rejects_overlong_structured_output(style_profile, message_context) -> None:
    decision = ComposeDecision(
        status="ready",
        drafts=[
            Draft(label="brief", body="too long"),
            Draft(label="warm", body="also too long"),
            Draft(label="formal", body="still too long"),
        ],
    )
    responses = FakeResponses([decision])
    generator = OpenAIMessageGenerator(client=SimpleNamespace(responses=responses))
    constrained = message_context.model_copy(update={"max_characters": 5})

    with pytest.raises(ValueError, match="exceeded"):
        generator.compose(style_profile, constrained)


def test_style_profile_schema_does_not_store_sample_bodies(style_profile) -> None:
    assert "samples" not in StyleProfile.model_fields
    assert "John's private news" not in style_profile.model_dump_json()
