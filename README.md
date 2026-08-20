# People Messenger

People Messenger is the message-composition and delivery core for a small,
voice-driven Raspberry Pi device. It learns a writing profile from a few of
your real messages, asks only for context that materially affects a message,
creates three tailored drafts, supports refinements, and requires a deliberate
two-second hardware-button hold before delivery.

The package is channel-neutral. It includes:

- an OpenAI-backed style analyzer, composer, refiner, and audio transcriber;
- a deterministic device state machine matching the hardware flow;
- X user search and one-to-one DM adapters;
- a local JSONL outbox for safe development and demos;
- one-time, message-bound confirmation tokens that prevent accidental sends.

## Quick start

Python 3.11 or newer is recommended.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
Copy-Item .env.example .env
```

Set `OPENAI_API_KEY` in your shell or load `.env` with your preferred secret
manager. Do not commit `.env`.

Put two or more samples of messages you actually wrote in separate text files,
then generate a local voice profile:

```powershell
people-messenger learn-voice samples\email-1.txt samples\dm-1.txt -o voice.json
```

Create drafts. If important context is missing, the command asks follow-up
questions and then regenerates:

```powershell
people-messenger compose `
  --profile voice.json `
  --channel x `
  --recipient-id 1234567890 `
  --recipient-name "John Doe" `
  --relationship "recruiter who interviewed me today" `
  --purpose "Thank him for the interview and say I would like to stay in touch"
```

Transcribe a USB-microphone recording:

```powershell
people-messenger transcribe recording.wav
```

Search X profiles after setting `X_BEARER_TOKEN`:

```powershell
people-messenger search-x "John Doe recruiter Toronto"
```

The CLI intentionally stops at review. Actual delivery is called by the device
controller only after `SEND` press and release events prove the button was held
for at least two seconds. See `examples/device_flow.py` for the GPIO integration
boundary.

## X setup

X profile search uses `GET /2/users/search`. Sending uses
`POST /2/dm_conversations/with/:participant_id/messages`. Configure:

- `X_BEARER_TOKEN` for public profile search;
- `X_USER_ACCESS_TOKEN` for DMs, with `dm.write`, `dm.read`, `tweet.read`, and
  `users.read` scopes.

The access token is never written to disk by this project. The local outbox is
the default during development.

## Algorithm

1. Learn stylistic patterns from user-authored samples. Samples are treated as
   untrusted data, never as instructions.
2. Combine the profile with the selected recipient, relationship, purpose,
   known facts, desired outcome, channel, and requested tone.
3. Ask up to three concise questions only when missing details would force the
   model to invent facts or could materially change the message.
4. Produce brief, warm, and formal variants. The prompt forbids invented facts,
   promises, credentials, relationships, and identity claims.
5. Refine only the selected draft while preserving verified facts and voice.
6. Bind the exact recipient, channel, and text to a short-lived one-time token.
7. Deliver only if the physical `SEND` button stays down for at least two
   seconds. Tokens cannot be replayed or used after editing the message.

## Development

```powershell
pytest
ruff check .
```

All API clients are behind small interfaces, so the tests use fakes and never
make network calls or send messages.
