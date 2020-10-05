import asyncio

import logging
from aiohttp import ClientSession, DummyCookieJar

from cashier.config import config
from cashier.fio import get_transactions
from cashier.xcontest import get_flights, Takeoff

log = logging.getLogger()


async def main():
    setup_logging()

    # TODO

    transactions = get_transactions(config["DATE"].year)
    for transaction in transactions:
        print(transaction)

    print("=" * 80)

    async with ClientSession(**config.get_namespace("HTTP_"), cookie_jar=DummyCookieJar()) as session:
        flights = get_flights(session, Takeoff.DOUBRAVA, config["DATE"].strftime("%Y-%m"))
        async for flight in flights:
            print(flight)


def setup_logging():
    if log.handlers:  # remove AWS default handler if present
        for handler in log.handlers:
            log.removeHandler(handler)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s.%(msecs)03d [%(levelname)s] %(module)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )


def lambda_entrypoint(event, context):
    """This function is called when invoked through AWS Lambda."""
    asyncio.run(main())


if __name__ == "__main__":
    """This is called as a Docker entrypoint."""
    asyncio.run(main())
