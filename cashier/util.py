import functools
import logging

from aiocron import crontab

log = logging.getLogger(__name__)


def cron_task(cron_pattern, run_after_startup=False):
    """
    Make a function to act like a cron task.
    """
    # this outer-level function just binds its params

    def make_cron_task(cron_fn):
        task_name = cron_fn.__name__

        @functools.wraps(cron_fn)
        async def wrapper(*args, **kwargs):
            log.info(f"Starting {task_name} task")
            must_wait = False
            while True:
                # handle `run_after_startup` + periodic waiting
                if must_wait or not run_after_startup:
                    await crontab(cron_pattern).next()
                must_wait = True

                # call the original function
                log.info(f"Executing {task_name} task")
                await cron_fn(*args, **kwargs)

        return wrapper

    return make_cron_task


def err_to_answer(err_types=(ValueError,)):
    """
    Catch unhandled errors of given type and convert them to Telegram answers.
    """

    def make_wrapper(fn):
        @functools.wraps(fn)
        async def wrapper(message, *args, **kwargs):
            try:
                return await fn(message, *args, **kwargs)
            except err_types as e:
                return await message.answer(f"{str(e)}. Please see /help")

        return wrapper

    return make_wrapper
