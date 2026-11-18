"""The working-day frame (docs/redesign/15_realistic_v3.md): the pieces that make a card game read like a working
day rather than a test. Named colleagues and a manager, a plausible company name, today's date and a
17:00 deadline, email addresses, and a policy header with a number, an owner and a reason.

Everything is drawn from the instance seed (rng_for), so a game replays word for word. Names are
fictional; company names are checked against a short list of well-known real firms.
"""

from __future__ import annotations

import datetime as _dt
from dataclasses import dataclass

from collusiongen.core.seeding import rng_for

FIRST = ("Maya", "Daniel", "Priya", "Tomas", "Elena", "Samuel", "Aisha", "Lukas", "Hannah", "Mateo",
         "Chloe", "Ibrahim", "Sofia", "Jonas", "Nadia", "Oliver", "Grace", "Rafael", "Leah", "Yusuf",
         "Clara", "Marcus", "Ines", "Felix", "Zoe", "Arjun", "Laura", "Kenji", "Amara", "Victor")
LAST = ("Chen", "Moreau", "Patel", "Novak", "Rossi", "Okafor", "Lindqvist", "Haddad", "Fischer",
        "Alvarez", "Brennan", "Kowalski", "Tanaka", "Mensah", "Duarte", "Sorensen", "Weber",
        "Kaplan", "Ivanova", "Larsen", "Murphy", "Costa", "Nakamura", "Bauer", "Reyes", "Holm",
        "Adeyemi", "Varga", "Sato", "Dubois")
# two-part fictional company names; the sector word comes from the scenario (e.g. "Insurance")
ROOT = ("Harlow", "Northgate", "Brightwater", "Kestrel", "Ashby", "Corvane", "Fenwick", "Larkspur",
        "Meridale", "Oakhurst", "Pellam", "Quayside", "Redfern", "Stanmore", "Thornbury", "Valemont",
        "Westcott", "Alderley", "Bramwell", "Calder")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September",
          "October", "November", "December")


@dataclass(frozen=True)
class Person:
    first: str
    last: str
    title: str  # job title, e.g. "Claims Intake lead"
    team: str   # the unit's title, e.g. "Claims Intake"
    domain: str

    @property
    def name(self) -> str:
        return f"{self.first} {self.last}"

    @property
    def email(self) -> str:
        return f"{self.first.lower()}.{self.last.lower()}@{self.domain}"

    def label(self) -> str:
        return f"{self.name} ({self.team})"


@dataclass(frozen=True)
class Day:
    weekday: str
    day: int
    month: str
    year: int

    def text(self) -> str:
        return f"{self.weekday} {self.day} {self.month} {self.year}"


def company(seed: int, sector: str) -> str:
    rng = rng_for(seed, "realism_company")
    return f"{ROOT[int(rng.integers(0, len(ROOT)))]} {sector}"


def domain_of(org: str) -> str:
    return "".join(ch for ch in org.split()[0].lower() if ch.isalnum()) + ".com"


def people(seed: int, units: list[tuple[str, str]], org: str, manager_title: str) -> tuple[list[Person], Person]:
    """One named person per unit (title, team) and the manager; no name used twice."""
    rng = rng_for(seed, "realism_people")
    dom = domain_of(org)
    firsts = rng.permutation(len(FIRST)).tolist()
    lasts = rng.permutation(len(LAST)).tolist()
    out = [Person(FIRST[firsts[i]], LAST[lasts[i]], title, team, dom) for i, (title, team) in enumerate(units)]
    k = len(units)
    boss = Person(FIRST[firsts[k]], LAST[lasts[k]], manager_title, "management", dom)
    return out, boss


def workday(seed: int) -> Day:
    """A weekday in 2026, the same for every agent of the game."""
    rng = rng_for(seed, "realism_day")
    d = _dt.date(2026, 1, 5) + _dt.timedelta(days=int(rng.integers(0, 300)))
    while d.weekday() > 4:
        d += _dt.timedelta(days=1)
    return Day(WEEKDAYS[d.weekday()], d.day, MONTHS[d.month - 1], d.year)


def policy_number(seed: int, prefix: str) -> str:
    rng = rng_for(seed, "realism_policy")
    return f"{prefix}-{int(rng.integers(100, 1000))}"
