from __future__ import annotations

import pytest

from people_messenger.models import Channel, MessageContext, Recipient, StyleProfile


@pytest.fixture
def style_profile() -> StyleProfile:
    return StyleProfile(
        greeting_style="Uses the recipient's first name",
        closing_style="Short sign-off",
        formality="balanced",
        warmth="warm",
        directness="direct",
        typical_sentence_length="short",
        uses_contractions=True,
        emoji_frequency="rare",
        punctuation_notes="Light punctuation",
        capitalization_notes="Standard capitalization",
        characteristic_phrases=["Thanks again"],
        tendencies_to_avoid=["Flowery language"],
    )


@pytest.fixture
def message_context() -> MessageContext:
    return MessageContext(
        recipient=Recipient(identifier="12345", display_name="John Doe", handle="johndoe"),
        channel=Channel.X,
        purpose="Thank John for today's interview and say I would like to stay in touch.",
        relationship="Recruiter who interviewed me today",
        known_facts=["I enjoyed learning about the role"],
        desired_outcome="Stay in touch",
    )
