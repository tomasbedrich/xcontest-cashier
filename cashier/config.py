from llconfig import Config
from llconfig.converters import bool_like
from pathlib import Path

config = Config()

# Keep README in sync!

config.init("TELEGRAM_BOT_TOKEN", str, None)
config.init("TELEGRAM_CHAT_ID", int, None)

config.init("XCONTEST_USERNAME", str, None)
config.init("XCONTEST_PASSWORD", str, None)

config.init("SENTRY_DSN", str, None)
config.init("SENTRY_ENVIRONMENT", str, "production")

# https://crontab.guru/
config.init("TRANSACTION_WATCH_CRON", str, "0 * * * *")  # each hour
config.init("FLIGHT_WATCH_CRON", str, "0 20 * * *")  # every day at 20:00
config.init("FLIGHT_WATCH_DAYS_BACK", int, 30)

config.init("RUN_TASKS_AFTER_STARTUP", bool_like, False)  # if True, first run tasks and then wait for next CRON

# https://www.whatismybrowser.com/guides/the-latest-user-agent/chrome
config.init("USER_AGENT", str, "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.114 Safari/537.36")

config.init("LIVENESS", Path, Path("/tmp/liveness"))
config.init("LIVENESS_SLEEP", int, 20)  # seconds

config.init("FIO_API_TOKEN", str, None)

config.init("MONGO_CONNECTION_STRING", str, None)
config.init("MONGO_DATABASE", str, "cashier")

config.load()
