import asyncio
import logging

from cashier.telegram_bot import main

log = logging.getLogger(__name__)

logging.basicConfig(level=logging.DEBUG, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
log.info("Starting")
try:
    asyncio.run(main())
except KeyboardInterrupt:
    log.info("Keyboard interrupt - terminating")
