from dataclasses import dataclass
from typing import Iterable, Optional

import logging
from fiobank import FioBank

from cashier.config import config

log = logging.getLogger()

bank = FioBank(token=config["FIO_API_TOKEN"])


@dataclass()
class Transaction:
    amount: float
    account_name: str
    recipient_message: Optional[str]

    @classmethod
    def from_api(cls, api_object):
        return cls(
            amount=api_object["amount"],
            account_name=api_object["account_name"] or api_object["executor"],
            recipient_message=api_object["recipient_message"],
        )


def get_transactions(year: int) -> Iterable[Transaction]:
    """Get all transactions in given year."""
    from_date = f"{year}-01-01"
    to_date = f"{year + 1}-01-01"
    acc_number = bank.info()["account_number_full"]
    log.info(f"Downloading transactions {from_date=} {to_date=} from bank account {acc_number}.")
    transactions = bank.period(from_date, to_date)
    return map(Transaction.from_api, transactions)


if __name__ == "__main__":
    for transaction in get_transactions(config["DATE"].year):
        print(transaction)
