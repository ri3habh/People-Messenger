from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Channel(StrEnum):
    X = "x"
    EMAIL = "email"
    SMS = "sms"
    OTHER = "other"


class Recipient(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    identifier: str = Field(min_length=1, description="Channel-specific stable ID or address")
    display_name: str = Field(min_length=1)
    handle: str | None = None
    bio: str | None = None
    location: str | None = None


class MessageContext(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    recipient: Recipient
    channel: Channel
    purpose: str = Field(min_length=1)
    relationship: str | None = None
    known_facts: list[str] = Field(default_factory=list)
    desired_outcome: str | None = None
    requested_tone: str | None = None
    additional_context: list[str] = Field(default_factory=list)
    max_characters: int | None = Field(default=None, ge=20, le=100_000)


class StyleProfile(BaseModel):
    """A compact description of style, not a copy of sample contents."""

    greeting_style: str
    closing_style: str
    formality: Literal["casual", "balanced", "formal"]
    warmth: Literal["reserved", "balanced", "warm"]
    directness: Literal["direct", "balanced", "indirect"]
    typical_sentence_length: Literal["short", "medium", "long"]
    uses_contractions: bool
    emoji_frequency: Literal["never", "rare", "sometimes", "often"]
    punctuation_notes: str
    capitalization_notes: str
    characteristic_phrases: list[str] = Field(default_factory=list, max_length=8)
    tendencies_to_avoid: list[str] = Field(default_factory=list, max_length=8)


class Draft(BaseModel):
    label: Literal["brief", "warm", "formal"]
    body: str = Field(min_length=1)


class ComposeDecision(BaseModel):
    status: Literal["needs_context", "ready", "refused"]
    questions: list[str] = Field(default_factory=list, max_length=3)
    drafts: list[Draft] = Field(default_factory=list, max_length=3)
    refusal_reason: str | None = None

    @model_validator(mode="after")
    def validate_status_payload(self) -> ComposeDecision:
        if self.status == "needs_context" and not self.questions:
            raise ValueError("needs_context requires at least one question")
        if self.status == "ready":
            labels = {draft.label for draft in self.drafts}
            if labels != {"brief", "warm", "formal"} or len(self.drafts) != 3:
                raise ValueError("ready requires exactly brief, warm, and formal drafts")
        if self.status == "refused" and not self.refusal_reason:
            raise ValueError("refused requires a reason")
        return self


class DeliveryReceipt(BaseModel):
    channel: Channel
    recipient_id: str
    provider_message_id: str
    status: Literal["queued", "sent"]


class XProfile(BaseModel):
    id: str
    name: str
    username: str
    description: str | None = None
    location: str | None = None
    profile_image_url: str | None = None
    verified: bool = False
