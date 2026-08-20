from __future__ import annotations

import json

from people_messenger.models import Recipient
from people_messenger.x_api import XDirectMessageSender, XProfileSearch


def test_x_profile_search_builds_v2_request() -> None:
    seen = []

    def transport(request):
        seen.append(request)
        return {
            "data": [
                {
                    "id": "123",
                    "name": "John Doe",
                    "username": "john",
                    "description": "Recruiter",
                    "verified": False,
                }
            ]
        }

    profiles = XProfileSearch("search-token", transport).search("John Doe recruiter", 10)

    assert profiles[0].username == "john"
    assert seen[0].full_url.startswith("https://api.x.com/2/users/search?")
    assert seen[0].get_header("Authorization") == "Bearer search-token"


def test_x_dm_sender_builds_confirmed_one_to_one_request() -> None:
    seen = []

    def transport(request):
        seen.append(request)
        return {"data": {"dm_event_id": "event-9"}}

    sender = XDirectMessageSender("user-token", transport)
    receipt = sender.send(Recipient(identifier="987", display_name="John"), "Hello John")

    request = seen[0]
    assert request.full_url.endswith("/2/dm_conversations/with/987/messages")
    assert request.method == "POST"
    assert json.loads(request.data) == {"text": "Hello John"}
    assert receipt.provider_message_id == "event-9"
