from typing import Optional

from aiogram.utils.emoji import emojize

from cashier.const import CMD_PAIR, CMD_NOTIFY
from cashier.models.membership import Membership
from cashier.models.transaction import Transaction
from cashier.osloveni import osloveni


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
        lines.append(
            f"Pairing command: <code>/{CMD_PAIR} {transaction.id} &lt;MEMBERSHIP_TYPE&gt; &lt;PILOT_USERNAME&gt;</code>"
        )
    return "\n".join(lines)


def offending_flight_msg(flight):
    lines = [
        "<strong>Offending flight:</strong>",
        flight.link,
        f"Notify command: <code>/{CMD_NOTIFY} {flight.id}</code>",
    ]
    return "\n".join(lines)


def unpaid_fee_msg(flight, signature):
    return f"""Ahoj {osloveni(flight.pilot.name.split(" ")[0])},

Píšu Ti jménem PG klubu Plzeň. Na základě automatizované kontroly pilotů, kteří (ne)mají zaplacené startovací poplatky nám vyběhl Tvůj let: {flight.link}.

Můžeme Tě zpětně poprosit o zaplacení poplatku? Jestli si vybereš denní / roční, to je na Tobě. Všechny detaily k platbě najdeš zde: https://pgplzen.cz/

Děkujeme! Přispěješ tím na nájem startovacích a přistávacích ploch, jejich údržbu a provoz meteo sond.

Za klub, {signature}"""


def start_msg():
    return emojize("Keep calm, I am working 24/7. :sunglasses:")


def help_msg():
    lines = [
        f"<code>/{CMD_PAIR} &lt;TRANSACTION_ID&gt; &lt;MEMBERSHIP_TYPE&gt; &lt;PILOT_USERNAME&gt;</code> - pair a transaction to a pilot (create a membership of given type)",
        f"<code>/{CMD_NOTIFY} &lt;FLIGHT_ID&gt;</code> - notify a pilot about unpaid fees (based on given flight)",
    ]
    return "\n".join(lines)
