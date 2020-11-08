import asyncio
import functools
import logging
import re
from datetime import timedelta, date
from typing import Optional

import pymongo
import sentry_sdk
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import CommandStart, CommandHelp, IDFilter
from aiohttp import ClientSession, DummyCookieJar, ClientTimeout
from fiobank import FioBank
from motor.core import AgnosticCollection as MongoCollection
from motor.motor_asyncio import AsyncIOMotorClient
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from cashier.config import config
from cashier.telegram_bot.const import CMD_PAIR, CMD_COMMENT
from cashier.telegram_bot.models import TransactionStorage, MembershipStorage, FlightStorage, Transaction, Membership
from cashier.telegram_bot.views import new_transaction_msg, help_msg, start_msg, offending_flight_msg
from cashier.util import cron_task, err_to_answer
from cashier.xcontest import Takeoff, Pilot, Flight

# telemetry
log = logging.getLogger(__name__)
sentry_sdk.init(**config.get_namespace("SENTRY_"), integrations=[AioHttpIntegration()])

# Telegram
CHAT_ID = config["TELEGRAM_CHAT_ID"]
bot = Bot(token=config["TELEGRAM_BOT_TOKEN"])
dispatcher = Dispatcher(bot)
CMD_PAIR_REGEX = re.compile(
    "".join(
        (
            r"^",
            r"(?P<transaction_id>\d+)\s+",
            "".join((r"(?P<membership_type>", "|".join([t.value for t in Membership.Type]), r")\s+")),
            r"(?P<pilot_username>\S+)",
            r"$",
        )
    )
)

session: Optional[ClientSession] = None
membership_storage: Optional[MembershipStorage] = None

# Mongo
mongo_client: Optional[AsyncIOMotorClient] = None
db: Optional[MongoCollection] = None


# FIXME
def get_db():
    global mongo_client, db
    if db is None:
        mongo_client = AsyncIOMotorClient(config["MONGO_CONNECTION_STRING"])
        db = mongo_client.default
    return db


cron_task = functools.partial(cron_task, run_after_startup=config["RUN_TASKS_AFTER_STARTUP"])
guarded_message_handler = functools.partial(dispatcher.message_handler, IDFilter(chat_id=CHAT_ID))


# Step 1
# Get a transaction from the bank account
@cron_task(config["TRANSACTION_WATCH_CRON"])
async def watch_transactions(trans_storage: TransactionStorage):
    for trans in await trans_storage.get_new_transactions():
        asyncio.create_task(process_transaction(trans_storage, trans))


# Step 2
# Backup a transaction to DB and request operators to pair a transaction.
async def process_transaction(trans_storage: TransactionStorage, trans: Transaction):
    """Process a single transaction which happened on the bank account."""
    log.info(f"Processing {trans}")
    await trans_storage.store_transaction(trans)
    try:
        membership_type = Membership.Type.from_amount(trans.amount)
    except ValueError:
        membership_type = None
    msg = new_transaction_msg(trans, membership_type)
    await bot.send_message(CHAT_ID, msg, parse_mode="HTML")


async def _parse_pair_args(args: str) -> Membership:
    """
    Parse a pair command arguments and return a populated membership object.

    Example args: `23461558143 YEARLY tomasbedrich`
    """
    log.info("Parsing a pair command")

    match = CMD_PAIR_REGEX.search(args)
    if not match:
        raise ValueError("Pairing command doesn't match expected format")
    command_data = match.groupdict()

    transaction_id = command_data["transaction_id"]
    membership_type = Membership.Type.from_str(command_data["membership_type"])
    pilot = Pilot(username=command_data["pilot_username"])
    await pilot.load_id(session)

    return Membership(transaction_id, membership_type, pilot)


# Step 3
# Pair a transaction (= create a membership)
@guarded_message_handler(commands=[CMD_PAIR])
@err_to_answer(ValueError)
async def pair(message: types.Message):
    membership = await _parse_pair_args(message.get_args())
    log.info(f"Creating {membership}")
    await membership_storage.create_membership(membership)
    await message.answer("Okay, paired")


@cron_task(config["FLIGHT_WATCH_CRON"])
async def watch_flights(flight_storage, membership_storage):
    takeoff = Takeoff.DOUBRAVA  # TODO watch all Takeoffs
    day = date.today() - timedelta(days=config["FLIGHT_WATCH_DAYS_BACK"])
    async for flight in flight_storage.get_new_flights(takeoff, day):
        asyncio.create_task(process_flight(flight_storage, membership_storage, flight))


async def process_flight(flight_storage: FlightStorage, membership_storage: MembershipStorage, flight: Flight):
    exists = await flight_storage.does_flight_exist(flight.id)
    if exists:
        log.info(f"Skipping {flight} as it is already processed")
        return
    else:
        log.info(f"Processing {flight}")
    membership = await membership_storage.get_by_flight(flight)
    if not membership:
        log.debug(f"No membership found for flight {flight.id}, reporting")
        msg = offending_flight_msg(flight)
        asyncio.create_task(bot.send_message(CHAT_ID, msg, parse_mode="HTML"))
    else:
        log.debug(f"Found membership for flight {flight.id}: {membership}")
        # following updates are idempotent
        await membership_storage.set_used_for(membership, flight)

    await flight_storage.store_flight(flight)


@guarded_message_handler(CommandStart())
async def start(message: types.Message):
    await message.answer(start_msg(), parse_mode="HTML")


@guarded_message_handler(CommandHelp())
async def help_(message: types.Message):
    await message.answer(help_msg(), parse_mode="HTML")


@guarded_message_handler(commands=[CMD_COMMENT])
async def comment(message: types.Message):
    # TODO
    await message.answer("Not implemented yet")


async def touch_liveness_probe():
    log.info("Starting liveness touch loop")
    while True:
        config["LIVENESS"].touch()
        await asyncio.sleep(config["LIVENESS_SLEEP"])


async def handle_telegram():
    # startup message + cleanup copied from aiogram.executor
    user = await dispatcher.bot.me
    log.info(f"Starting Telegram bot: {user.full_name} [@{user.username}]")

    # this call blocks
    await dispatcher.start_polling(reset_webhook=True)

    await dispatcher.storage.close()
    await dispatcher.storage.wait_closed()
    await dispatcher.bot.close()


def handle_exception(loop, context):
    if "exception" in context:
        log.exception("Unhandled exception", exc_info=context["exception"])
    else:
        log.error("Unhandled exception: %s", context["message"])

    if loop.is_closed():
        return

    log.info("Shutting down all running tasks")
    for task in asyncio.all_tasks():
        task.cancel()


async def _smoke_test_mongo():
    log.info(f"Smoke testing connection to Mongo")
    await get_db().transactions.find_one()


async def setup_mongo_indices():
    await asyncio.gather(
        get_db().flights.create_index([("id", pymongo.DESCENDING)], unique=True),
        get_db().transactions.create_index([("id", pymongo.DESCENDING)], unique=True),
        get_db().membership.create_index([("transaction_id", pymongo.DESCENDING)], unique=True),
    )


async def main():
    global membership_storage, flight_storage, session

    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_exception)

    await _smoke_test_mongo()
    await setup_mongo_indices()

    # TODO close session
    session = ClientSession(
        timeout=ClientTimeout(total=10),
        raise_for_status=True,
        cookie_jar=DummyCookieJar(),
        headers={"User-Agent": config["USER_AGENT"]},
    )

    bank = FioBank(config["FIO_API_TOKEN"])

    trans_storage = TransactionStorage(bank, get_db().transactions)
    membership_storage = MembershipStorage(get_db().membership)
    flight_storage = FlightStorage(session, get_db().flights)

    asyncio.create_task(touch_liveness_probe(), name="touch_liveness_probe")
    asyncio.create_task(watch_transactions(trans_storage), name="watch_transactions")
    asyncio.create_task(watch_flights(flight_storage, membership_storage), name="watch_flights")
    await handle_telegram()
