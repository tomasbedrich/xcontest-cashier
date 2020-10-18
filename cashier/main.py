import asyncio

import logging
from collections import defaultdict
from typing import Iterable, Optional

from aiohttp import ClientSession, DummyCookieJar
from fuzzywuzzy import process, fuzz

from cashier.config import config
from cashier.fio import get_transactions, Transaction
from cashier.xcontest import get_flights, Takeoff, Pilot

log = logging.getLogger()


class TransactionStorage:

    def __init__(self):
        self._by_account_name = defaultdict(list)
        self._by_recipient_message = defaultdict(list)

    def feed(self, transactions: Iterable[Transaction]):
        """Feed the storage with Transaction objects."""
        for transaction in transactions:
            if transaction.amount <= 0:
                # Don't process outgoing payments at all.
                continue
            self._by_account_name[transaction.account_name].append(transaction)
            if transaction.recipient_message and transaction.recipient_message.strip():
                # Don't add empty messages to recipient message matching storage.
                self._by_recipient_message[transaction.recipient_message].append(transaction)

    def get_by_username(self, username: str) -> Optional[Iterable[Transaction]]:
        # We are using fuzzy matching to allow deviances like prefixes ("payment for:"), lower/upper case, typos, etc.
        transactions, score, recipient_message = process.extractOne(username, self._by_recipient_message, scorer=fuzz.token_set_ratio)
        log.debug(f"Best username match for '{username}' among all transactions is: {recipient_message} ({score=})")
        return transactions if score >= config["PAIRING_THRESHOLD"] else None

    def get_by_name(self, name: str) -> Optional[Iterable[Transaction]]:
        # Here we also use fuzzy matching because of different given names and surnames order, university titles, abbreviations, etc.
        transactions, score, account_name = process.extractOne(name, self._by_account_name, scorer=fuzz.token_set_ratio)
        log.debug(f"Best real name match for '{name}' among all transactions is: {account_name} ({score=})")
        return transactions if score >= config["PAIRING_THRESHOLD"] else None

    def get_by_pilot(self, pilot: Pilot) -> Optional[Iterable[Transaction]]:
        # Username should be a primary pairing method - pilots are requested to write their username into a transaction recipient message.
        transactions = self.get_by_username(pilot.username)
        if not transactions:
            # As a secondary method we match pilot's real name with account names of transactions.
            transactions = self.get_by_name(pilot.name)
        return transactions


async def main():
    setup_logging()

    ts = TransactionStorage()
    ts.feed(get_transactions(config["DATE"].year))

    async with ClientSession(**config.get_namespace("HTTP_"), cookie_jar=DummyCookieJar()) as session:
        # flights = get_flights(session, Takeoff.DOUBRAVA, config["DATE"].strftime("%Y-%m")) # FIXME
        flights = get_flights(session, Takeoff.DOUBRAVA, "2020-06")
        async for flight in flights:
            log.debug(f"Processing flight {flight}")
            pilot_transactions = ts.get_by_pilot(flight.pilot)
            # FIXME: If the pilot has ANY transactions, we consider the fee paid.
            if pilot_transactions:
                log.info(f"Fee for flight {flight} has been paid.")
            else:
                log.warning(f"Fee for flight {flight} is unpaid.")


def setup_logging():
    if log.handlers:  # remove AWS default handler if present
        for handler in log.handlers:
            log.removeHandler(handler)
    logging.basicConfig(
        level=logging.DEBUG,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(module)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def lambda_entrypoint(event, context):
    """This function is called when invoked through AWS Lambda."""
    asyncio.run(main())


if __name__ == "__main__":
    """This is called as a Docker entrypoint."""
    asyncio.run(main())
