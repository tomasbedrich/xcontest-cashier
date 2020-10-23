import asyncio
import logging
import sentry_sdk
from aiocron import crontab
from aiogram import Bot, Dispatcher, types
from aiogram.dispatcher.filters import CommandStart, CommandHelp, IDFilter
from aiogram.utils import executor
from aiohttp import ClientSession, DummyCookieJar
from datetime import datetime
from sentry_sdk.integrations.aiohttp import AioHttpIntegration
from textwrap import dedent
from typing import Optional

from cashier.fio import get_transactions
from cashier.xcontest import get_flights, Takeoff
from .config import config

log = logging.getLogger(__name__)

sentry_sdk.init(**config.get_namespace("SENTRY_"), integrations=[AioHttpIntegration()])

bot = Bot(token=config["TOKEN"])
dp = Dispatcher(bot)

tasks = []

session: Optional[ClientSession] = None

CMD_PAIR = "sparuj"
CMD_COMMENT = "vyhubuj"


async def on_startup(dispatcher: Dispatcher):
    global session
    log.info("Opening an HTTP session")
    session = ClientSession(**config.get_namespace("HTTP_"), cookie_jar=DummyCookieJar())  # TODO set User-Agent

    log.info("Starting tasks")
    # tasks.append(asyncio.create_task(watch_transactions()))
    tasks.append(asyncio.create_task(touch_liveness_probe()))


async def on_shutdown(dispatcher: Dispatcher):
    log.info("Closing an HTTP session")
    if session:
        await session.close()
    log.info("Stopping tasks")
    for task in tasks:
        task.cancel()


async def watch_transactions():
    while True:
        log.info("Executing transaction watch task")

        transactions = get_transactions(datetime.today().year)
        for transaction in transactions:
            # FIXME not printing, don't know why
            log.debug(f"bot.send_message({config['CHAT_ID']=}, {transaction=})")
            # await bot.send_message(config["CHAT_ID"], str(transaction))

        await crontab(config["TRANSACTION_WATCH_CRON"]).next()


async def watch_takeoffs():
    while True:
        log.info("Executing takeoff watch task")

        flights = get_flights(session, Takeoff.DOUBRAVA, datetime.today().strftime("%Y-%m"))
        # async for flight in flights:
        #     # FIXME not printing, don't know why
        #     log.debug(f"bot.send_message({config['CHAT_ID']=}, {flight=})")
        #     # await bot.send_message(config["CHAT_ID"], str(flight))

        await crontab(config["TAKEOFF_WATCH_CRON"]).next()


@dp.message_handler(CommandStart())
async def start(message: types.Message):
    await message.answer("Neboj, kasíruju pořád ;)")


@dp.message_handler(CommandHelp())
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


@dp.message_handler(IDFilter(chat_id=config["CHAT_ID"]))
@dp.message_handler(commands=[CMD_PAIR])
async def pair(message: types.Message):
    await message.answer("Ještě nefunguje")


@dp.message_handler(IDFilter(chat_id=config["CHAT_ID"]))
@dp.message_handler(commands=[CMD_COMMENT])
async def comment(message: types.Message):
    await message.answer("Ještě nefunguje")


async def touch_liveness_probe():
    while True:
        config["LIVENESS"].touch()
        await asyncio.sleep(config["LIVENESS_SLEEP"])


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    executor.start_polling(dp, on_startup=on_startup, on_shutdown=on_shutdown)


if __name__ == "__main__":
    main()
