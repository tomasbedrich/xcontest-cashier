import asyncio
import fiobank
import logging
import sentry_sdk
from aiocron import crontab
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import CommandStart, CommandHelp, IDFilter
from aiogram.utils import emoji
from aiogram.utils.markdown import escape_md
from aiohttp import ClientSession, DummyCookieJar, ClientTimeout
from datetime import timedelta, date
from fiobank import FioBank
from motor.motor_asyncio import AsyncIOMotorClient
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from textwrap import dedent

from cashier.config import config
from cashier.fio import transaction_to_json
from cashier.xcontest import Takeoff, get_flights

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


async def send_md(message):
    """Send Markdown message to a common chat."""
    message = emoji.emojize(dedent(message))
    await bot.send_message(CHAT_ID, message, parse_mode="MarkdownV2")


async def watch_transactions(bank, db):
    log.info("Starting transaction watch task")
    while True:
        await crontab(config["TRANSACTION_WATCH_CRON"]).next()
        log.info(f"Executing transaction watch task")

        last_transaction = await db.transactions.find_one(sort=[("transaction_id", -1)])
        from_id = last_transaction["transaction_id"]
        log.debug(f"Downloading last transactions {from_id=}")
        retry = 3
        while True:
            try:
                transactions = list(await asyncio.to_thread(bank.last, from_id=from_id))
                break
            except fiobank.ThrottlingError:
                log.warning("Throttled bank API request, retrying in 30 seconds")
                await asyncio.sleep(30)  # hardcoded according to FIO bank docs
            except:  # NOQA
                # for whatever else reason it fails, retry a few times
                if retry == 0:
                    raise
                log.exception(f"Downloading transactions failed, retrying {retry} more times")
                retry -= 1
                await asyncio.sleep(5)

        if not transactions:
            log.info("No transactions downloaded")
            continue

        for trans in transactions:
            log.info(f"Processing transaction {trans}")
            db.transactions.insert_one(transaction_to_json(trans))
            message = escape_md(trans["recipient_message"])
            from_ = escape_md(trans["account_name"] or trans["executor"])
            amount = escape_md(int(trans["amount"]))
            bot_say = fr"""
            *Nový pohyb na účtu:*
            :question: {amount} Kč \- {message} \({from_}\)
            """
            asyncio.create_task(send_md(bot_say))


async def watch_flights(session, db):
    log.info("Starting flight watch task")
    while True:
        await crontab(config["FLIGHT_WATCH_CRON"]).next()
        log.info("Executing flight watch task")

        last_flight = await db.flights.find_one(sort=[("datetime", -1)])

        takeoff = Takeoff.DOUBRAVA
        day = date.today() - timedelta(days=config["FLIGHT_WATCH_DAYS_BACK"])
        log.debug(f"Downloading flights from {day} for {takeoff}")
        flights = get_flights(session, takeoff, day)

        has_flights = False
        async for flight in flights:
            has_flights = True
            log.info(f"Processing flight {flight}")
            if flight.datetime <= last_flight["datetime"]:
                continue
            db.flights.insert_one(flight.as_dict())

        if not has_flights:
            log.info("No flights downloaded")


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

    logging.info("Shutting down all running tasks")
    for task in asyncio.all_tasks():
        task.cancel()


async def main():
    loop = asyncio.get_event_loop()
    loop.set_exception_handler(handle_exception)

    mongo_client = AsyncIOMotorClient(config["MONGO_CONNECTION_STRING"])
    db = mongo_client.default

    bank = FioBank(config["FIO_API_TOKEN"])

    asyncio.create_task(touch_liveness_probe(), name="touch_liveness_probe")
    asyncio.create_task(watch_transactions(bank, db), name="watch_transactions")
    async with ClientSession(
        timeout=ClientTimeout(total=10),
        raise_for_status=True,
        cookie_jar=DummyCookieJar(),
        headers={"User-Agent": config["USER_AGENT"]},
    ) as session:
        loop.create_task(watch_flights(session, db), name="watch_flights")
    await handle_telegram()


if __name__ == "__main__":
    logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    log.info("Starting")
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Keyboard interrupt - terminating")
