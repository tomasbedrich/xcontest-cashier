from dataclasses import dataclass
from enum import Enum

import asyncio
import datetime
import logging
from aiohttp import ClientSession, DummyCookieJar
from bs4 import BeautifulSoup, SoupStrainer
from typing import Union, Iterable, AsyncIterable
from urllib.parse import urljoin

log = logging.getLogger()


class Takeoff(Enum):
    DOUBRAVA = 13.2028, 49.4328
    SVIHOV = 13.2672, 49.4933
    KOTEROV = 13.4348, 49.7216


@dataclass()
class Pilot:
    username: str
    name: str

    def __eq__(self, other):
        if isinstance(other, Pilot):
            return self.username == other.username
        return NotImplemented

    def __hash__(self):
        return hash(self.username)


@dataclass(frozen=True)
class Flight(object):
    link: str
    pilot: Pilot

    @classmethod
    def from_table_row(cls, row: BeautifulSoup):
        # link = "/world/cs/prelety/detail:Lopper/17.5.2020/14:02"
        link = row.select_one(".detail")["href"]
        if not (link.startswith("http://") or link.startswith("https://")):
            link = urljoin("https://www.xcontest.org", link)

        pilot_username = link.split("/")[-3].split(":")[1]
        pilot_name = row.select_one(".plt").text
        pilot = Pilot(username=pilot_username, name=pilot_name)

        return cls(link=link, pilot=pilot)

    def __eq__(self, other):
        if isinstance(other, Flight):
            return self.link == other.link
        return NotImplemented


def post_flight_comment(flight_id, comment):
    # TODO
    pass


async def get_flights(
    session: ClientSession, takeoff: Takeoff, date: Union[datetime.date, str], *, sleep: int = 2
) -> AsyncIterable[Flight]:
    """
    Get all flights for given takeoff and date.

    Handle pagination in background and yield populated Flight objects.
    """
    log.info(f"Downloading flights for {date=}, {takeoff=}.")
    async for page in _download_pages(session, takeoff, date, sleep=sleep):
        for flight in _parse_page(page):
            yield flight


async def _download_pages(
    session: ClientSession, takeoff: Takeoff, date: Union[datetime.date, str], sleep: int
) -> AsyncIterable[str]:
    """
    Download 0-N pages of flights belonging to given start place for given date.

    Uses Worldwide flight search page on Xcontest.
    Flights are sorted ascending to start date.
    Date can be either ISO 8601, or YYYY-MM pattern representing whole month.
    """
    lat, lon = takeoff.value
    if isinstance(date, datetime.date):
        date = date.isoformat()

    offset, has_next = 0, True
    while has_next:
        url = f"https://www.xcontest.org/world/cs/vyhledavani-preletu/?list[sort]=time_start&list[dir]=up&list[start]={offset}&filter[point]={lat}%20{lon}&filter[mode]=START&filter[date]={date}&filter[date_mode]=dmy"
        page = await (await session.get(url)).text()
        yield page
        if has_next := _has_next_page(page):
            offset += 50  # hardcoded to match xcontest
            await asyncio.sleep(sleep)


def _has_next_page(page: str) -> bool:
    soup = BeautifulSoup(page, "lxml", parse_only=SoupStrainer("div", {"class": "paging"}))

    paging_items = soup.select_one(".paging")
    if not paging_items:
        # handle empty result
        return False

    # we must filter out side arrows (.pg-edge)
    # if last item is current, there are no more pages
    # current page is not a link, it is <strong>
    return "<strong>" != paging_items.select(":not(.pg-edge)")[-1].name


def _parse_page(page: str) -> Iterable[Flight]:
    """Given a page as a HTML string, yield flights found on the page."""
    soup = BeautifulSoup(page, "lxml", parse_only=SoupStrainer("table", {"class": "flights"}))
    for row in soup.select(".flights tbody tr"):
        yield Flight.from_table_row(row)


async def _main():
    from cashier.config import config

    async with ClientSession(**config.get_namespace("HTTP_"), cookie_jar=DummyCookieJar()) as session:
        async for flight in get_flights(session, Takeoff.DOUBRAVA, "2020-05"):
            print(flight)


if __name__ == "__main__":
    asyncio.run(_main())
