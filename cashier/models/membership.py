import dataclasses
import datetime
import enum
import logging
import uuid
from typing import Optional

import pymongo
from motor.core import AgnosticCollection as MongoCollection

from cashier.util import NoPublicConstructor
from cashier.xcontest import Pilot, Flight

log = logging.getLogger(__name__)


@dataclasses.dataclass()
class Membership:
    transaction_id: str
    type: "Type"
    pilot: Pilot
    id: uuid.UUID = dataclasses.field(default_factory=uuid.uuid4)
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
            """Return membership type based on amounts agreed by the club board."""
            if amount in (100, 150):
                return cls.daily
            if amount == 500:
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
            id=obj["id"],
            date_paired=datetime.date.fromisoformat(obj["date_paired"]) if obj["date_paired"] else None,
            used_for=obj.get("used_for"),
        )


class MembershipStorage(metaclass=NoPublicConstructor):
    def __init__(self, db_collection):
        self.db_collection = db_collection

    @classmethod
    async def new(cls, db_collection: MongoCollection):
        await db_collection.create_index([("id", pymongo.DESCENDING)], unique=True)
        return cls._create(db_collection)

    async def create_membership(self, membership: Membership):
        """
        Create a membership.
        """
        log.info(f"Creating {membership}")
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
            {"id": membership.id},
            {"$set": {"used_for": used_for}},  # NOQA - let's crash if `used_for` is not set, this shouldn't happen
        )
