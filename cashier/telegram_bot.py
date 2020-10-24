import asyncio
import logging
import sentry_sdk
from aiocron import crontab
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import CommandStart, CommandHelp, IDFilter
from aiohttp import ClientSession, DummyCookieJar, ClientTimeout
from datetime import datetime, date
from fiobank import FioBank
from motor.motor_asyncio import AsyncIOMotorClient
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from textwrap import dedent

from cashier.config import config
from cashier.fio import get_transactions
from cashier.xcontest import get_flights, Takeoff

# telemetry
log = logging.getLogger(__name__)
sentry_sdk.init(**config.get_namespace("SENTRY_"), integrations=[AioHttpIntegration()])

# Telegram
CHAT_ID = config["TELEGRAM_CHAT_ID"]
bot = Bot(token=config["TELEGRAM_BOT_TOKEN"])
dispatcher = Dispatcher(bot)

# constants
CMD_PAIR = "sparuj"
CMD_COMMENT = "vyhubuj"


async def watch_transactions(bank, db):
    while True:
        log.info("Executing transaction watch task")

        transactions = await asyncio.to_thread(get_transactions, bank, "2020-01-01", date.today())
        # await db.transactions.insertMany(transactions)
        for transaction in transactions:
            print(transaction)
            # await bot.send_message(CHAT_ID, str(transaction))

        await crontab(config["TRANSACTION_WATCH_CRON"]).next()


async def watch_flights(session):
    while True:
        log.info("Executing flight watch task")

        flights = get_flights(session, Takeoff.DOUBRAVA, datetime.today().strftime("%Y-%m"))
        await db.flights.insertMany(flights)
        # async for flight in flights:
        #     # FIXME not printing, don't know why
        #     log.debug(f"bot.send_message({CHAT_ID=}, {flight=})")
        #     # await bot.send_message(CHAT_ID, str(flight))

        await crontab(config["FLIGHT_WATCH_CRON"]).next()


@dispatcher.message_handler(CommandStart())
async def start(message: types.Message):
    await message.answer("Neboj, kasíruju pořád ;)")


@dispatcher.message_handler(CommandHelp())
async def help_(message: types.Message):
    await message.answer(
        dedent(
            fr"""
    `/{CMD_PAIR} <ID_PLATBY> <XCONTEST-UZIVATEL>` \- TODO \- spáruje platbu k uživateli
    `/{CMD_COMMENT} <ID_LETU>` \- TODO \- napíše zamračený komentář k letu
    """
        ),
        parse_mode="MarkdownV2",
    )


@dispatcher.message_handler(IDFilter(chat_id=CHAT_ID))
@dispatcher.message_handler(commands=[CMD_PAIR])
async def pair(message: types.Message):
    await message.answer("Ještě nefunguje")


@dispatcher.message_handler(IDFilter(chat_id=CHAT_ID))
@dispatcher.message_handler(commands=[CMD_COMMENT])
async def comment(message: types.Message):
    await message.answer("Ještě nefunguje")


async def touch_liveness_probe():
    log.info("Starting liveness touch loop")
    while True:
        config["LIVENESS"].touch()
        await asyncio.sleep(config["LIVENESS_SLEEP"])


async def handle_telegram():
    # FIXME temporary deactivated
    while True:
        await asyncio.sleep(99)

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
        log.error("Unhandled exception: %s" % context["message"])


async def main():
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_exception)

    mongo_client = AsyncIOMotorClient(config["MONGO_CONNECTION_STRING"])
    db = mongo_client.default

    bank = FioBank(config["FIO_API_TOKEN"])

    asyncio.create_task(touch_liveness_probe(), name="touch_liveness_probe")
    asyncio.create_task(watch_transactions(bank, db), name="watch_transactions")
    async with ClientSession(
        timeout=ClientTimeout(total=10), raise_for_status=True, cookie_jar=DummyCookieJar()
    ) as session:  # TODO set User-Agent
        pass
        # loop.create_task(watch_flights(session, db), name="watch_flights")
    await handle_telegram()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log.info("Starting")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Terminating")
