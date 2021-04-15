import asyncio
import functools
import logging
import random
import re
from datetime import timedelta, date

import sentry_sdk
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import CommandStart, CommandHelp, IDFilter
from aiogram.utils.exceptions import RetryAfter, RestartingTelegram
from aiohttp import ClientSession, ClientTimeout, ClientError
from fiobank import FioBank
from motor.core import AgnosticCollection as MongoCollection
from motor.motor_asyncio import AsyncIOMotorClient
from sentry_sdk.integrations.aiohttp import AioHttpIntegration

from cashier.config import config
from cashier.const import CMD_PAIR, CMD_NOTIFY
from cashier.models.flight import FlightStorage
from cashier.models.membership import Membership, MembershipStorage
from cashier.models.transaction import Transaction, TransactionStorage
from cashier.util import cron_task
from cashier.views import new_transaction_msg, help_msg, start_msg, offending_flight_msg, unpaid_fee_msg
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
CMD_NOTIFY_REGEX = re.compile(r"^(?P<flight_id>\d+)$")

cron_task = functools.partial(cron_task, run_after_startup=config["RUN_TASKS_AFTER_STARTUP"])


def guarded_message_handler(*custom_filters, **kwargs):
    filters = (IDFilter(chat_id=CHAT_ID),) + kwargs.get("custom_filters", custom_filters)

    def decorator(callback):
        dispatcher.register_message_handler(callback, *filters, **kwargs)
        dispatcher.register_edited_message_handler(callback, *filters, **kwargs)
        return callback

    return decorator


async def _send_message(*args, **kwargs):
    """Send a Telegram message handling retries if needed."""
    while True:
        try:
            return await bot.send_message(*args, **kwargs)
        except RetryAfter as e:
            # this happens quite often since we may post many flights during a spike
            await asyncio.sleep(e.timeout + random.uniform(0, 10))
        except RestartingTelegram:
            await asyncio.sleep(10 + random.uniform(0, 10))


# Step 1
# Get a transaction from the bank account.
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
    await _send_message(CHAT_ID, msg, parse_mode="HTML")


async def _parse_pair_args(session: ClientSession, args: str) -> Membership:
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
# Pair a transaction (= create a membership).
# We would normally decorate this with @guarded_message_handler, but we need to bind `session` and `membership_storage`,
# therefore we register this in `handle_telegram()`
async def pair(session, membership_storage, message: types.Message):
    try:
        membership = await _parse_pair_args(session, message.get_args())
        await membership_storage.create_membership(membership)
    except (ValueError, ClientError) as e:
        return await message.answer(f"{str(e)}. Please see /help")
    await message.answer("Okay, paired")


@cron_task(config["FLIGHT_WATCH_CRON"])
async def watch_flights(flight_storage, membership_storage):
    # TODO add backoff when XContest is down
    day = date.today() - timedelta(days=config["FLIGHT_WATCH_DAYS_BACK"])
    # beware that `Takeoff` is passed as iterable
    async for flight in flight_storage.get_flights(day, Takeoff):
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
        asyncio.create_task(_send_message(CHAT_ID, msg, parse_mode="HTML"))
    else:
        log.debug(f"Found membership for flight {flight.id}: {membership}")
        # following updates are idempotent
        await membership_storage.set_used_for(membership, flight)

    await flight_storage.store_flight(flight)


def _parse_notify_args(args: str) -> str:
    log.info("Parsing a notify command")

    match = CMD_NOTIFY_REGEX.search(args)
    if not match:
        raise ValueError("Notify command doesn't match expected format")
    command_data = match.groupdict()

    return command_data["flight_id"]


# Notify a pilot about unpaid fees.
# We would normally decorate this with @guarded_message_handler, but we need to bind `session` and `flight_storage`,
# therefore we register this in `handle_telegram()`
async def notify(session, flight_storage, message: types.Message):
    try:
        flight_id = _parse_notify_args(message.get_args())
    except ValueError as e:
        return await message.answer(f"{str(e)}. Please see /help")

    try:
        flight = await flight_storage.get_flight(flight_id)
        if not flight:
            raise ValueError("Flight with given ID wasn't found.")
    except ValueError as e:
        return await message.answer(str(e))

    msg = unpaid_fee_msg(flight, message.from_user.full_name)
    # TODO actual DM sending + confirmation before send?
    await message.answer(
        f'<strong>I would have sent following message to <a href="{flight.pilot.private_message_url}">{flight.pilot.username}</a>:</strong>\n\n{msg}',
        disable_web_page_preview=True,
        parse_mode="HTML",
    )


@guarded_message_handler(CommandStart())
async def start(message: types.Message):
    await message.answer(start_msg(), parse_mode="HTML")


@guarded_message_handler(CommandHelp())
async def help_(message: types.Message):
    await message.answer(help_msg(), parse_mode="HTML")


async def touch_liveness_probe():
    log.info("Starting liveness touch loop")
    while True:
        config["LIVENESS"].touch()
        await asyncio.sleep(config["LIVENESS_SLEEP"])


async def handle_telegram(session: ClientSession, flight_storage: FlightStorage, membership_storage: MembershipStorage):
    guarded_message_handler(commands=[CMD_PAIR])(functools.partial(pair, session, membership_storage))
    # TODO we need logged in session
    guarded_message_handler(commands=[CMD_NOTIFY])(functools.partial(notify, session, flight_storage))

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


class Container:
    """Dependency container for clean resource management."""

    db: MongoCollection
    session: ClientSession
    bank: FioBank
    transaction_storage: TransactionStorage
    membership_storage: MembershipStorage
    flight_storage: FlightStorage

    def __init__(self):
        db_client = AsyncIOMotorClient(config["MONGO_CONNECTION_STRING"])
        self.db = db_client[config["MONGO_DATABASE"]]
        self.bank = FioBank(config["FIO_API_TOKEN"])

    async def __aenter__(self) -> "Container":
        self.session = ClientSession(
            timeout=ClientTimeout(total=10), raise_for_status=True, headers={"User-Agent": config["USER_AGENT"]},
        )
        self.transaction_storage = await TransactionStorage.new(self.bank, self.db.transactions)
        self.membership_storage = await MembershipStorage.new(self.db.membership)
        self.flight_storage = await FlightStorage.new(self.session, self.db.flights)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.session.close()


async def main():
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_exception)
    asyncio.create_task(touch_liveness_probe(), name="touch_liveness_probe")

    async with Container() as c:
        asyncio.create_task(watch_transactions(c.transaction_storage), name="watch_transactions")
        asyncio.create_task(watch_flights(c.flight_storage, c.membership_storage), name="watch_flights")
        await handle_telegram(c.session, c.flight_storage, c.membership_storage)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    logging.getLogger("cashier").setLevel(logging.DEBUG)
    log.info("Starting")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Keyboard interrupt - terminating")
