from typing import Optional

import emoji

from cashier.telegram_bot.const import CMD_PAIR
from cashier.telegram_bot.models import Transaction, Membership


def new_transaction_msg(transaction: Transaction, membership: Optional[Membership]):
    """
    Render a new transaction message.

    Based on whether membership is passed, renders also a pairing command suggestion.

    If the transaction contains a message, it is used as a pilot username for a pairing command.
    """
    icon = emojize(":white_check_mark:" if membership else ":question:")
    lines = [
        "<strong>New transaction:</strong>",
        f"{icon} {transaction.amount} Kč from {transaction.from_} - {transaction.message or '(no message)'}",
    ]
    if membership:
        pilot_username = transaction.message if transaction.message else "&lt;PILOT_USERNAME&gt;"
        lines.append(f"Pairing command: <code>/{CMD_PAIR} {transaction.id_} {membership.value} {pilot_username}</code>")
    else:
        lines.append("Membership type not detected. Please resolve manually.")
    return "\n".join(lines)
