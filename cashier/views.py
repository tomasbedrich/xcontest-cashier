from typing import Optional

from aiogram.utils.emoji import emojize

from cashier.const import CMD_PAIR, CMD_COMMENT
from cashier.models.membership import Membership
from cashier.models.transaction import Transaction


def new_transaction_msg(transaction: Transaction, membership_type: Optional[Membership.Type]):
    """
    Render a new transaction message.

    Based on whether membership is passed, renders also a pairing command suggestion.

    If the transaction contains a message, it is used as a pilot username for a pairing command.
    """
    icon = emojize(":white_check_mark:" if membership_type else ":question:")
    lines = [
        "<strong>New transaction:</strong>",
        f"{icon} {transaction.amount} Kč from {transaction.from_} - {transaction.message or '(no message)'}",
    ]
    if membership_type:
        pilot_username = transaction.message if transaction.message else "&lt;PILOT_USERNAME&gt;"
        lines.append(
            f"Pairing command: <code>/{CMD_PAIR} {transaction.id} {membership_type.value} {pilot_username}</code>"
        )
    else:
        lines.append("Membership type not detected. Please resolve manually.")
    return "\n".join(lines)


def offending_flight_msg(flight):
    lines = [
        "<strong>Offending flight:</strong>",
        flight.link,
        f"Comment command: <code>/{CMD_COMMENT} {flight.id}</code>",
    ]
    return "\n".join(lines)


def start_msg():
    return emojize("Keep calm, I am working 24/7. :sunglasses:")


def help_msg():
    lines = [
        f"<code>/{CMD_PAIR} &lt;TRANSACTION_ID&gt; &lt;MEMBERSHIP_TYPE&gt; &lt;PILOT_USERNAME&gt;</code> - pair a transaction to a pilot (create a membership of given type)",
        f"<code>/{CMD_COMMENT} &lt;FLIGHT_ID&gt;</code> - write an angry comment to the flight",
    ]
    return "\n".join(lines)
