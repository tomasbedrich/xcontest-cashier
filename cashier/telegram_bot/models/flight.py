import asyncio
import logging
from typing import AsyncIterable

from aiohttp import ClientSession
from motor.core import AgnosticCollection as MongoCollection

from cashier.xcontest import Flight, get_flights

log = logging.getLogger(__name__)


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
