from aiohttp import ClientTimeout
from llconfig import Config
from llconfig.converters import bool_like
from pathlib import Path

config = Config()

config.init("TOKEN", str, None)
config.init("CHAT_ID", int, None)

config.init("HTTP_TIMEOUT", lambda val: ClientTimeout(total=int(val)), ClientTimeout(total=10))  # seconds
config.init("HTTP_RAISE_FOR_STATUS", bool_like, True)

config.init("SENTRY_DSN", str, None)
config.init("SENTRY_ENVIRONMENT", str, "production")

# https://crontab.guru/
config.init("TRANSACTION_WATCH_CRON", str, "0 19 * * *")  # daily at 19:00
config.init("TAKEOFF_WATCH_CRON", str, "0 20 1 * *")  # monthly on 1st at 20:00

config.init("LIVENESS", Path, Path("/tmp/liveness"))
config.init("LIVENESS_SLEEP", int, 10)  # seconds

config.init("FIO_API_TOKEN", str, None)

config.init("MONGO_CONNECTION_STRING", str)

config.load()
