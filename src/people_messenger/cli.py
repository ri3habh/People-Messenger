from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .ai import OpenAIMessageGenerator, read_samples
from .models import Channel, MessageContext, Recipient, StyleProfile
from .transcription import OpenAITranscriber
from .x_api import XProfileSearch


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="people-messenger")
    subparsers = parser.add_subparsers(dest="command", required=True)

    learn = subparsers.add_parser("learn-voice", help="Build a style profile from sample files")
    learn.add_argument("samples", nargs="+", type=Path)
    learn.add_argument("-o", "--output", required=True, type=Path)

    compose = subparsers.add_parser("compose", help="Create tailored drafts")
    compose.add_argument("--profile", required=True, type=Path)
    compose.add_argument("--channel", choices=[item.value for item in Channel], required=True)
    compose.add_argument("--recipient-id", required=True)
    compose.add_argument("--recipient-name", required=True)
    compose.add_argument("--recipient-handle")
    compose.add_argument("--relationship")
    compose.add_argument("--purpose", required=True)
    compose.add_argument("--fact", action="append", default=[])
    compose.add_argument("--desired-outcome")
    compose.add_argument("--tone")
    compose.add_argument("--max-characters", type=int)

    transcribe = subparsers.add_parser("transcribe", help="Transcribe an audio file")
    transcribe.add_argument("audio", type=Path)

    search = subparsers.add_parser("search-x", help="Search X profiles")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    return parser


def _learn_voice(args: argparse.Namespace) -> int:
    generator = OpenAIMessageGenerator()
    profile = generator.learn_voice(read_samples(args.samples))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(profile.model_dump_json(indent=2), encoding="utf-8")
    print(f"Saved voice profile to {args.output}")
    return 0


def _compose(args: argparse.Namespace) -> int:
    profile = StyleProfile.model_validate_json(args.profile.read_text(encoding="utf-8"))
    context = MessageContext(
        recipient=Recipient(
            identifier=args.recipient_id,
            display_name=args.recipient_name,
            handle=args.recipient_handle,
        ),
        channel=Channel(args.channel),
        purpose=args.purpose,
        relationship=args.relationship,
        known_facts=args.fact,
        desired_outcome=args.desired_outcome,
        requested_tone=args.tone,
        max_characters=args.max_characters,
    )
    generator = OpenAIMessageGenerator()
    decision = generator.compose(profile, context)
    rounds = 0
    while decision.status == "needs_context" and rounds < 2:
        print("A little more context is needed:")
        answers = [input(f"- {question}\n> ").strip() for question in decision.questions]
        question_answers = [
            f"Question: {question}\nAnswer: {answer}"
            for question, answer in zip(decision.questions, answers, strict=True)
            if answer
        ]
        context = context.model_copy(
            update={"additional_context": [*context.additional_context, *question_answers]}
        )
        decision = generator.compose(profile, context)
        rounds += 1
    if decision.status == "refused":
        print(f"Cannot compose this request: {decision.refusal_reason}", file=sys.stderr)
        return 2
    if decision.status != "ready":
        print("Still missing essential context; no message was generated.", file=sys.stderr)
        return 2
    for index, draft in enumerate(decision.drafts, 1):
        print(f"\n[{index}] {draft.label.upper()}\n{draft.body}")
    print("\nReview only: this command does not send messages.")
    return 0


def _search_x(args: argparse.Namespace) -> int:
    profiles = XProfileSearch().search(args.query, args.limit)
    print(json.dumps([profile.model_dump() for profile in profiles], indent=2, ensure_ascii=False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "learn-voice":
            return _learn_voice(args)
        if args.command == "compose":
            return _compose(args)
        if args.command == "transcribe":
            print(OpenAITranscriber().transcribe(args.audio))
            return 0
        if args.command == "search-x":
            return _search_x(args)
    except (FileNotFoundError, ValueError, RuntimeError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
