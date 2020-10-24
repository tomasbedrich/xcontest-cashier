from dataclasses import dataclass

import logging
import os
from datetime import date
from fiobank import FioBank
from typing import Iterable, Optional

log = logging.getLogger(__name__)


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


def get_transactions(bank, from_date, to_date) -> Iterable[Transaction]:
    acc_number = bank.info()["account_number_full"]
    log.info(f"Downloading transactions {from_date=} {to_date=} from bank account {acc_number}.")
    transactions = bank.period(from_date, to_date)
    return map(Transaction.from_api, transactions)


# KISS
def transaction_to_json(trans):
    return {
        **trans,
        "date": trans["date"].isoformat()
    }


if __name__ == "__main__":
    token = os.environ["APP_FIO_API_TOKEN"]
    bank = FioBank(token)
    for transaction in get_transactions(bank, "2020-01-01", date.today()):
        print(transaction)
