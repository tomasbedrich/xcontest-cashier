import asyncio
import dataclasses
import datetime
import logging
import re
from enum import Enum
from typing import Union, Iterable, AsyncIterable, Optional
from urllib.parse import urljoin

from aiohttp import ClientSession, ClientTimeout
from bs4 import BeautifulSoup, SoupStrainer

log = logging.getLogger(__name__)

_pilot_id_cache = {}


class Takeoff(Enum):
    DOUBRAVA = 13.2028, 49.4328
    SVIHOV = 13.2672, 49.4933
    KOTEROV = 13.4348, 49.7216


@dataclasses.dataclass()
class Pilot:
    username: str
    name: Optional[str] = None
    id: Optional[int] = None

    async def load_id(self, session: ClientSession):
        """
        Load ID for pilot by username.

        Raises:
            ClientError: When there is an error during loading HTTP request.
            ValueError: When pilot ID cannot be found.
        """
        if self.username in _pilot_id_cache:
            self.id = _pilot_id_cache[self.username]
            return

        detail = await (await session.get(self.url)).text()
        match = re.search(r'XContest\.run\("pilot", .*item : (\d+)', detail, re.DOTALL)
        if not match:
            raise ValueError("Cannot find the pilot ID by a username, it probably doesn't exist")

        self.id = int(match[1])
        _pilot_id_cache[self.username] = self.id
        log.debug(f"Fetched ID for {self}")

    @property
    def url(self):
        return "https://www.xcontest.org/world/en/pilots/detail:" + self.username

    @property
    def private_message_url(self):
        return f"https://www.xcontest.org/world/en/private-messages:{self.username}#thread-create"

    def __eq__(self, other):
        if isinstance(other, Pilot):
            return self.username == other.username
        return NotImplemented

    def __hash__(self):
        return hash(self.username)

    def as_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, obj: dict):
        return cls(username=obj["username"], name=obj.get("name"), id=obj.get("id"),)

    async def send_private_message(self, session: ClientSession, message):
        # TODO
        pass


@dataclasses.dataclass(frozen=True)
class Flight(object):
    id: str
    link: str
    pilot: Pilot
    datetime: datetime.datetime

    @classmethod
    def from_table_row(cls, row: BeautifulSoup):
        # <td title="FLID:2235393">...</td>
        id_ = row.find("td")["title"].split(":")[-1]

        # <a class="detail" title="detail letu" href="/world/cs/prelety/detail:Bull77/3.9.2020/14:45">...</a>
        link = row.select_one(".detail")["href"]
        if not (link.startswith("http://") or link.startswith("https://")):
            link = urljoin("https://www.xcontest.org", link)

        pilot_username = link.split("/")[-3].split(":")[1]
        # <a class="plt" href="/world/cs/piloti/detail:Bull77">Tomáš Jirka</a>
        pilot_name = row.select_one(".plt").text
        pilot = Pilot(username=pilot_username, name=pilot_name)

        date, time = link.split("/")[-2], link.split("/")[-1]
        dt = datetime.datetime.strptime(f"{date} {time}", "%d.%m.%Y %H:%M")

        return cls(id=id_, link=link, pilot=pilot, datetime=dt)

    def __eq__(self, other):
        if isinstance(other, Flight):
            return self.link == other.link
        return NotImplemented

    def as_dict(self):
        return dataclasses.asdict(self)

    @classmethod
    def from_dict(cls, obj):
        return cls(
            id=obj["id"],
            link=obj["link"],
            pilot=Pilot.from_dict(obj["pilot"]),
            datetime=obj["datetime"],
        )


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

async def login(session: ClientSession, username: str, password: str):
    """
    Login to the XContest   
    """
    log.info("Logging to XContest...")    
    url = "https://www.xcontest.org/world/en/"    
    payload = {'login[username]':username, 'login[password]':password, 'login[persist_login]' : 'Y'}
    await session.post(url, data=payload)    

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
        res = await session.get(url)
        page = await res.text()
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
    import os

    async with ClientSession(
        timeout=ClientTimeout(total=10),
        raise_for_status=True
    ) as session:
        async for flight in get_flights(session, Takeoff.DOUBRAVA, "2020-10-18"):
            print(flight.as_dict())

if __name__ == "__main__":
    asyncio.run(_main())