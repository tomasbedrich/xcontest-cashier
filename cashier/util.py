import functools
import logging
from typing import Type, Any, TypeVar

from aiocron import crontab

T = TypeVar("T")

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


# https://stackoverflow.com/a/64682734/570503


class NoPublicConstructor(type):
    """Metaclass that ensures a private constructor

    If a class uses this metaclass like this:

        class SomeClass(metaclass=NoPublicConstructor):
            pass

    If you try to instantiate your class (`SomeClass()`),
    a `TypeError` will be thrown.
    """

    def __call__(cls, *args, **kwargs):
        raise TypeError(f"{cls.__module__}.{cls.__qualname__} has no public constructor")

    def _create(cls: Type[T], *args: Any, **kwargs: Any) -> T:
        return super().__call__(*args, **kwargs)  # type: ignore
