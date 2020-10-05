from aiohttp import ClientTimeout
from datetime import date

from llconfig import Config
from llconfig.converters import bool_like

config = Config(env_prefix="CASHIER_")

config.init("HTTP_TIMEOUT", lambda val: ClientTimeout(total=int(val)), ClientTimeout(total=10))  # seconds
config.init("HTTP_RAISE_FOR_STATUS", bool_like, True)

config.init("FIO_API_TOKEN", str, None)

config.init("DATE", date, date.today())

config.load()
