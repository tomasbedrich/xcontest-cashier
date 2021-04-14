import asyncio
import logging
import random
from typing import AsyncIterable, Iterable

import pymongo
from aiohttp import ClientSession
from motor.core import AgnosticCollection as MongoCollection

from cashier.util import NoPublicConstructor
from cashier.xcontest import Takeoff, Flight, get_flights, login

log = logging.getLogger(__name__)


class FlightStorage(metaclass=NoPublicConstructor):
    def __init__(self, session, db_collection):
        self.session = session
        self.db_collection = db_collection
        await login(self.session, os.getenv("APP_XCONTEST_USERNAME"), os.getenv("APP_XCONTEST_PASSWORD"))

    @classmethod
    async def new(cls, session: ClientSession, db_collection: MongoCollection):
        await db_collection.create_index([("id", pymongo.DESCENDING)], unique=True)
        return cls._create(session, db_collection)

    async def get_flight(self, id_):
        res = await self.db_collection.find_one({"id": id_})
        return Flight.from_dict(res) if res else None

    async def get_flights(self, day, takeoffs: Iterable[Takeoff]) -> AsyncIterable[Flight]:
        """
        Get all flights for given date and takeoffs.

        Chain flights from all takeoffs into one iterable.
        """
        for takeoff in takeoffs:
            async for flight in self._get_flights_one_takeoff(day, takeoff):
                yield flight
            await asyncio.sleep(random.randint(5, 15))

    async def _get_flights_one_takeoff(self, day, takeoff: Takeoff) -> AsyncIterable[Flight]:
        """
        Get all flights for given date and takeoff (one).

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
