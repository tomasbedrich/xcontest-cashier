import asyncio
import dataclasses
import datetime
import logging
from typing import Optional, List

import fiobank
from motor.core import AgnosticCollection as MongoCollection

log = logging.getLogger(__name__)


@dataclasses.dataclass()
class Transaction:
    id: str
    amount: int
    from_: str
    message: Optional[str]
    date: datetime.date

    @classmethod
    def from_api(cls, api_object):
        return cls(
            id=api_object["transaction_id"],
            amount=int(api_object["amount"]),
            from_=api_object["account_name"] or api_object["executor"],
            message=api_object["recipient_message"],
            date=api_object["date"],
        )

    def as_dict(self):
        return {
            "id": self.id,
            "amount": self.amount,
            "from": self.from_,
            "message": self.message,
            "date": self.date.isoformat(),
        }


class TransactionStorage:
    def __init__(self, bank: fiobank.FioBank, db_collection: MongoCollection):
        self.bank = bank
        self.db_collection = db_collection

    async def get_new_transactions(self) -> List[Transaction]:
        """
        Fetch new transactions on a bank account.

        If there is at least one transaction in a DB, use it's ID as a marker from where to start downloading.
        Otherwise download all transactions from 2020-01-01.

        It throttled by a Fio Bank API, wait automatically 30 seconds (according their docs).

        In case of any other error, try 3 times, then fail.
        """
        last_transaction = await self.db_collection.find_one(sort=[("id", -1)])
        retry = 3
        while True:
            try:
                if last_transaction:
                    from_id = last_transaction["id"]
                    log.debug(f"Downloading last transactions {from_id=}")
                    transactions = await asyncio.to_thread(self.bank.last, from_id=from_id)
                else:
                    log.debug(f"Downloading all transactions from 2020-01-01")
                    transactions = await asyncio.to_thread(self.bank.last, from_date="2020-01-01")
                break
            except fiobank.ThrottlingError:
                log.warning("Throttled bank API request, retrying in 30 seconds")
                await asyncio.sleep(30)  # hardcoded according to the bank API docs
            except:  # NOQA
                # for whatever else reason it fails, retry a few times
                if retry == 0:
                    raise
                log.exception(f"Downloading transactions failed, retrying {retry} more times")
                retry -= 1
                await asyncio.sleep(5)

        transactions = list(map(Transaction.from_api, transactions))
        if transactions:
            log.info(f"Downloaded {len(transactions)} transactions")
        else:
            log.info("No transactions downloaded")
        return transactions

    async def store_transaction(self, transaction: Transaction):
        await self.db_collection.insert_one(transaction.as_dict())
