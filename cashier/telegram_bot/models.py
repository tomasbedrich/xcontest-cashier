import asyncio
import dataclasses
import datetime
import enum
import logging
from typing import List, Optional, AsyncIterable

import fiobank
from aiohttp import ClientSession
from motor.core import AgnosticCollection as MongoCollection

from cashier.xcontest import Pilot, get_flights, Flight

log = logging.getLogger(__name__)


@dataclasses.dataclass()
class Membership:
    transaction_id: str
    type: "Type"
    pilot: Pilot
    date_paired: datetime.date = dataclasses.field(default_factory=datetime.date.today)
    used_for: Optional[str] = None

    class Type(enum.Enum):
        daily = "DAILY"
        yearly = "YEARLY"

        @classmethod
        def from_str(cls, input_: str):
            try:
                return cls(input_.upper())
            except ValueError:
                raise ValueError(f"Membership must be either {cls.daily.value} or {cls.yearly.value}") from None

        @classmethod
        def from_amount(cls, amount: int):
            if amount == 50:
                return cls.daily
            if amount >= 100:  # FIXME set to board agreed amount (probably 250)
                return cls.yearly
            raise ValueError(f"Amount of {amount} doesn't correspond to any membership type")

    def as_dict(self):
        return {
            **dataclasses.asdict(self),
            "type": self.type.value,
            "date_paired": self.date_paired.isoformat() if self.date_paired else None,
        }

    @classmethod
    def from_dict(cls, obj):
        return cls(
            transaction_id=obj["transaction_id"],
            type=cls.Type.from_str(obj["type"]),
            pilot=Pilot.from_dict(obj["pilot"]),
            date_paired=datetime.date.fromisoformat(obj["date_paired"]) if obj["date_paired"] else None,
            used_for=obj.get("used_for"),
        )


class MembershipStorage:
    def __init__(self, db_collection: MongoCollection):
        self.db_collection = db_collection

    async def create_membership(self, membership: Membership):
        """
        Create a membership if doesn't exist yet.
        """
        if existing := await self.db_collection.find_one({"transaction_id": membership.transaction_id}):
            raise ValueError(
                f"This transaction is already paired as {existing['type']} for pilot {existing['pilot']['username']}"
            )
        await self.db_collection.insert_one(membership.as_dict())

    async def get_by_flight(self, flight: Flight) -> Optional[Membership]:
        """
        Return most suitable membership for given flight (its pilot).

        "Most suitable" means (in this order):

        1. Yearly membership bound to the year when the flight happened.
        2. Daily membership bound to the day when the flight happened.
        3. Unbound yearly membership.
        4. Unbound daily membership.
        5. `None` if none of above is found.
        """
        # some aliases to make Black happy
        search = self.db_collection.find_one
        base_filter = {"pilot.username": flight.pilot.username}
        flight_year = flight.datetime.year
        flight_date = flight.datetime.date().isoformat()

        # This can be probably solved by some fancy Mongo multi-column-index sorting feature...
        # But I just need to get the shit done.
        candidates = [
            search({**base_filter, "type": Membership.Type.yearly.value, "used_for": flight_year}),  # 1.
            search({**base_filter, "type": Membership.Type.daily.value, "used_for": flight_date}),  # 2.
            search({**base_filter, "type": Membership.Type.yearly.value, "used_for": None}),  # 3.
            search({**base_filter, "type": Membership.Type.daily.value, "used_for": None}),  # 4.
        ]
        for candidate in candidates:
            res = await candidate
            if res:
                return Membership.from_dict(res)
        return None  # 5.

    async def set_used_for(self, membership: Membership, flight: Flight):
        """
        Set membership to be used for given flight.
        """
        if membership.type == Membership.Type.yearly:
            used_for = flight.datetime.year
        elif membership.type == Membership.Type.daily:
            used_for = flight.datetime.date().isoformat()
        await self.db_collection.update_one(
            {"transaction_id": membership.transaction_id},
            {"$set": {"used_for": used_for}},  # NOQA - let's crash if `used_for` is not set, this shouldn't happen
        )


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


class FlightStorage:
    def __init__(self, session: ClientSession, db_collection: MongoCollection):
        self.session = session
        self.db_collection = db_collection

    async def get_flights(self, takeoff, day) -> AsyncIterable[Flight]:
        """
        Get all flights for given takeoff and date.

        In case of any error, try 3 times, then fail.
        """
        retry = 3
        while True:
            try:
                num = 0
                async for flight in get_flights(self.session, takeoff, day):
                    yield flight
                    num += 1
                log.info(f"Downloaded {num} flights")
                break
            except:  # NOQA
                # for whatever else reason it fails, retry a few times
                if retry == 0:
                    raise
                log.exception(f"Downloading flights failed, retrying {retry} more times")
                retry -= 1
                await asyncio.sleep(10)

    async def store_flight(self, flight: Flight):
        """
        Store a flight in the DB if it doesn't exist yet.
        """
        existing_flight = await self.db_collection.find_one({"id": flight.id})
        if existing_flight:
            return
        await self.db_collection.insert_one(flight.as_dict())

    async def does_flight_exist(self, id_):
        return bool(await self.db_collection.find_one({"id": id_}))
