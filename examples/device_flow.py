"""GPIO integration sketch.

Replace the simulated button timestamps with gpiozero Button.when_pressed and
Button.when_released callbacks. Recipient recording/search and display rendering
remain hardware-specific; the workflow owns state and confirmation safety.
"""

from pathlib import Path

from people_messenger.ai import OpenAIMessageGenerator
from people_messenger.delivery import ConfirmedDelivery, OutboxSender
from people_messenger.models import Channel
from people_messenger.workflow import MessengerWorkflow

generator = OpenAIMessageGenerator()
sender = OutboxSender(Path("outbox.jsonl"), channel=Channel.X)
delivery = ConfirmedDelivery({Channel.X: sender})
workflow = MessengerWorkflow(generator, delivery)


def on_send_pressed() -> None:
    if workflow.state == "confirming":
        workflow.press_send()


def on_send_released() -> None:
    if workflow.state == "confirming":
        receipt = workflow.release_send()
        if receipt:
            print(f"Delivered: {receipt.provider_message_id}")
        else:
            print("Hold SEND for two seconds to confirm")
