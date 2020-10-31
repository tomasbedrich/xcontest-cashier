import asyncio
import logging
from typing import List

import fiobank
from motor.core import AgnosticCollection as MongoCollection

log = logging.getLogger(__name__)


class TransactionStorage:
    def __init__(self, bank: fiobank.FioBank, db_collection: MongoCollection):
        self.bank = bank
        self.db_collection = db_collection

    async def get_new_transactions(self) -> List[dict]:
        """
        Fetch new transactions on a bank account.

        If there is at least one transaction in a DB, use it's ID as a marker from where to start downloading.
        Otherwise download all transactions from 2020-01-01.

        It throttled by a Fio Bank API, wait automatically 30 seconds (according their docs).

        In case of any error other, try 3 times, then fail.
        """
        last_transaction = await self.db_collection.find_one(sort=[("transaction_id", -1)])
        retry = 3
        while True:
            try:
                if last_transaction:
                    from_id = last_transaction["transaction_id"]
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

        transactions = list(transactions)
        if transactions:
            log.info(f"Downloaded {len(transactions)} transactions")
        else:
            log.info("No transactions downloaded")
        return transactions
