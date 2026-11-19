#!/usr/bin/env python3
"""Check legislative roles against official per-session rosters.

    uv run python .claude/skills/data-review/check_rosters.py BASE [SCOPE ...] [--all]
    uv run python .claude/skills/data-review/check_rosters.py --self-test

For every changed legislative role (--all: every role in scope) in a state with a roster
source below, finds each roster session the role spans and looks the person up in it.
Rosters are downloaded once into ~/.cache/openstates-data-review/rosters, so reruns are
offline and give the same answer. Tab-separated output: file, person, role, session,
verdict, roster district(s), source. Verdicts:

  roster-ok        the roster lists this surname in the role's chamber and district
  ROSTER-MISMATCH  the roster lists this surname in the chamber, but only in other
                   districts (in `expected`): the role's district is wrong for that
                   session, or a namesake holds the other seat
  roster-absent    the surname isn't in the chamber's roster: a gap in service, a
                   mid-term start or departure, a name the roster spells differently, or
                   a roster that missed the member (NH 2020: see `NH_2020`)
  no-roster        no roster source for this state and chamber

Matching is by surname, so a ROSTER-MISMATCH next to a same-surname member, or a
roster-absent for a member who goes by a different surname, needs a look at the source.
"""

import argparse
import datetime as dt
import hashlib
import html
import json
import re
import shutil
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

from extract_claims import changed_files, load

CACHE = Path.home() / ".cache" / "openstates-data-review" / "rosters"
LEGISLATIVE = {"upper", "lower"}
NH_JOURNALS = "https://gc.nh.gov/house/calendars_journals/journals/"
NH_COUNTIES = (
    "BELKNAP|CARROLL?|CHESHIRE|COOS|GRAFTON|HILLSBOROUGH|MERRIMACK|ROCKINGHAM|"
    "STRAFFORD|SULLIVAN"
)
NH_ABBR = {
    "Belk": "Belknap",
    "Carr": "Carroll",
    "Ches": "Cheshire",
    "Coos": "Coos",
    "Graf": "Grafton",
    "Hills": "Hillsborough",
    "Merr": "Merrimack",
    "Rock": "Rockingham",
    "Straf": "Strafford",
    "Sull": "Sullivan",
}
# NH House organization-day journals: every member sworn in, by county and district
NH_ORG_DAYS = {
    "2008-12-03": "2009/Daily Journal No 1 12-3-08-Organization Day final.pdf",
    "2010-12-01": "2010/Daily Journal #1, 12-1-10, Organization Day Final.pdf",
    "2012-12-05": "2013/No 06 December 05 2012.pdf",
    "2014-12-03": "2015/No 04 December 03 2014.pdf",
    "2016-12-07": "2017/No 01 December 7 2016.pdf",
    "2018-12-05": "2019/No 01 December 05 2018.pdf",
    "2020-12-02": "2021/No 01 December 02 2020.pdf",
    "2022-12-07": "2023/HJ 01 December 7, 2022.pdf",
    "2024-12-04": "2025/HJ 01 December 4, 2024.pdf",
}
# The 2020 organization day met outdoors (COVID) and about a third of members were sworn
# in remotely later, so its roster misses them. Bill-sponsor citations in the 2021-22
# journals ("Gilman, Rock. 18") give the rest their districts.
NH_2020 = [
    "2021/No 02 January 06 2021.pdf",
    "2021/No 03 February 24 2021.pdf",
    "2021/No 04 February 25 2021.pdf",
    "2021/No 05 April 07 2021.pdf",
    "2021/No 06 April 08 2021.pdf",
    "2021/No 07 April 09 2021.pdf",
    "2022/HJ 01 January 5, 2022.pdf",
    "2022/HJ 02 January 6, 2022.pdf",
    "2022/HJ 03 February 16, 2022.pdf",
    "2022/HJ 04 February 17, 2022.pdf",
    "2022/HJ 05 March 10, 2022.pdf",
]
AR_LIST = "https://www.arkleg.state.ar.us/Legislators/List?ddBienniumSession={y}%2F{y}R"
AK_LIST = "https://www.akleg.gov/basis/mbr_info.asp?session={n}"


def fetch(url):
    """The text of url (PDFs through pdftotext -layout), cached on disk."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / hashlib.sha256(url.encode()).hexdigest()[:20]
    if not path.exists():
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})  # noqa: S310
        with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310
            body = resp.read()
        if body.startswith(b"%PDF"):
            exe = shutil.which("pdftotext")
            if not exe:
                sys.exit("pdftotext (poppler) is needed for PDF rosters")
            body = subprocess.run(  # noqa: S603
                [exe, "-layout", "-", "-"], input=body, capture_output=True, check=True
            ).stdout
        path.write_bytes(body)
    return path.read_text(errors="replace")


def surname(name):
    """Lower-case ASCII last name, without suffixes (Jr., III) or a trailing party."""
    name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.sub(r"[^A-Za-z' -]", " ", name).replace("-", " ").lower().split()
    while len(words) > 1 and words[-1] in {"jr", "sr", "ii", "iii", "iv", "r", "d"}:
        words.pop()
    return words[-1].replace("'", "") if words else ""


def parse_nh_org_day(text):
    """[(chamber, district, surname)] from an NH organization-day journal roster."""
    rows, county, cur = [], None, None
    seats = {}
    for line in text.splitlines():
        m = re.match(rf"\s*({NH_COUNTIES})( COUNTY)?( \(\d+\))?\s*$", line)
        if m:
            county, cur = m.group(1).title().replace("Carrol", "Carroll"), None
            county = county.replace("Carrolll", "Carroll")
            continue
        m = re.match(r"\s*Dist\.? ?No\.? ?(\d+)(?: \(\d+\))?\s*(.*)", line)
        if m and county:
            cur = f"{county} {int(m.group(1))}"
            seats[cur] = m.group(2)
        elif cur and re.search(r"[;,] ?[rd]\b", line) and "HOUSE RECORD" not in line:
            seats[cur] += "; " + line.strip()  # the district's names wrapped a line
        else:
            cur = None
    for district, names in seats.items():
        for entry in names.split(";"):
            name = re.sub(r",\s*[rd]\s*$", "", entry.strip())
            if name:
                rows.append(("lower", district, surname(name)))
    return rows


def parse_nh_sponsors(text):
    """[(chamber, district, surname)] from 'Surname, Abbr. N' sponsor citations."""
    text = re.sub(r"\s+", " ", text)
    found = re.findall(
        r"([A-Z][A-Za-z'\u2019.\- ]{1,30}?), (" + "|".join(NH_ABBR) + r")\. ?(\d+)\b",
        text,
    )
    return [("lower", f"{NH_ABBR[c]} {int(d)}", surname(n)) for n, c, d in found]


def parse_ar(text):
    """[(chamber, district, surname)] from an arkleg biennium member list."""
    rows = []
    rx = (
        r'member=[^"]*">([^<]+)</a>.*?Chamber:</span>\s*(House|Senate)'
        r".*?District:</span>\s*(\d+)"
    )
    for name, house, district in re.findall(rx, text, re.S):
        chamber = "lower" if house == "House" else "upper"
        rows.append((chamber, district, surname(html.unescape(name))))
    return rows


def parse_ak(text):
    """[(chamber, district, surname)] from an akleg legislature member list."""
    rx = r">(Senator|Representative) ([^<]+?)\s*</nobr>.*?<TD align=center>\s*(\w+)\s*<"
    # namesakes get a first initial after the surname: "Stevens B", "Stevens G"
    return [
        (
            "upper" if title == "Senator" else "lower",
            district,
            surname(re.sub(r" [A-Z]$", "", name)),
        )
        for title, name, district in re.findall(rx, text, re.S)
    ]


def nh_sessions():
    for day, doc in NH_ORG_DAYS.items():
        url = NH_JOURNALS + urllib.parse.quote(doc)
        rows = parse_nh_org_day(fetch(url))
        if day.startswith("2020"):
            for extra in NH_2020:
                rows += parse_nh_sponsors(
                    fetch(NH_JOURNALS + urllib.parse.quote(extra))
                )
        yield day, url, rows


def ar_sessions():
    # terms start the 2nd Monday of January of odd years; the roster is the biennium's
    for year in range(2001, dt.date.today().year + 1, 2):
        url = AR_LIST.format(y=year)
        # the list includes members who resigned, so it covers the whole biennium
        yield f"{year}-02-01..{year + 2}-01-01", url, parse_ar(fetch(url))


def ak_sessions():
    # the 22nd Legislature convened in January 2001, and a new one every odd year
    for n in range(22, 22 + (dt.date.today().year - 2001) // 2 + 1):
        url = AK_LIST.format(n=n)
        yield f"{2001 + 2 * (n - 22)}-02-01", url, parse_ak(fetch(url))


def parse_wv(text):
    """[(chamber, district, surname)] from a WV Legislature membership directory.

    Members sit two per line, "Name (R - County)" (from 2021 "NAME (R) - COUNTY"), with
    "District N" on the next line. Senators come before the first @wvhouse.gov address;
    pages after the last one repeat names under the old district plan.
    """
    lines = text.splitlines()
    house = [i for i, line in enumerate(lines) if "@wvhouse.gov" in line]
    name_rx = re.compile(
        r"([A-Z][A-Za-z.'\u2019 \-]+?) \(([RDI])\)? ?- ?([A-Za-z .]+?)"
        r"(?:, District (\d+))?\)?(?=\s{2,}|$)",
        re.I,
    )
    rows = []
    for i, line in enumerate(lines[: house[-1] + 1]):
        names = [(m.start(), m.group(1), m.group(4)) for m in name_rx.finditer(line)]
        after = [x for x in lines[i + 1 : i + 3] if re.search(r"(?i)district \d+", x)]
        dists = [
            (m.start(), m.group(1))
            for m in re.finditer(r"(?i)district (\d+)", after[0] if after else "")
        ]
        for pos, name, inline in names:
            if not inline and not dists:
                continue
            district = inline or min(dists, key=lambda d: abs(d[0] - pos))[1]
            chamber = "lower" if i > house[0] - 15 else "upper"
            rows.append((chamber, str(int(district)), surname(name)))
    return rows


def parse_md(text, chamber):
    """[(chamber, district, surname)] from a Maryland Manual list by district."""
    text = re.sub(r"\s+", " ", text)
    rows = []
    for part in re.split(r"<b>\s*DISTRICT ", text)[1:]:
        if not (m := re.match(r"(\w+)", part)):
            continue
        district = m.group(1)
        for raw in re.findall(r'msa\d+\.html"?\s*>([^<]+)<', part):
            name = re.sub(r"\([A-Z]\)", "", html.unescape(raw)).strip()
            rows.append((chamber, district, surname(name)))
    return rows


def parse_me_house(text):
    """[(chamber, district, surname)] from a Maine House members-by-district history."""
    rx = r"District (\d+) - [^<]*?- ([^<]+?)\s*\((\w) -"  # a title may sit between
    return [("lower", d, surname(html.unescape(n))) for d, n, _ in re.findall(rx, text)]


def wv_sessions():
    # one directory per year, a snapshot of the members at the start of the session
    for year in range(2011, dt.date.today().year + 1):
        old = year <= 2020  # noqa: PLR2004 (the file name changed in 2021)
        name = f"membership_directory_{year}" if old else f"DIRECTORY_{year}"
        url = f"https://www.wvlegislature.gov/legisdocs/publications/info/{name}.pdf"
        yield f"{year}-02-01", url, parse_wv(fetch(url))


def md_sessions():
    # one Maryland Manual edition per year, updated through the year
    for year in range(2011, dt.date.today().year + 1):
        base = f"https://{year}mdmanual.msa.maryland.gov/msa/mdmanual/"
        house, senate = (
            base + "06hse/html/hsedist.html",
            base + "05sen/html/sendist.html",
        )
        rows = parse_md(fetch(house), "lower") + parse_md(fetch(senate), "upper")
        yield f"{year}-06-01", house, rows


def vt_sessions():
    # one list per biennium, named by its even year; it includes mid-term replacements
    for year in range(2010, dt.date.today().year + 2, 2):
        url = f"https://legislature.vermont.gov/people/loadAll/{year}"
        rows = []
        for p in json.loads(fetch(url))["data"]:
            district = re.sub(r" District$", "", p["District"] or "")
            if p["PersonTypeID"] == "S":
                district = district.replace("-", " ")
            chamber = "upper" if p["PersonTypeID"] == "S" else "lower"
            rows.append((chamber, district, surname(p["LastName"])))
        yield f"{year - 1}-02-01..{year}-12-31", url, rows


def sd_sessions():
    sessions = json.loads(fetch("https://sdlegislature.gov/api/Sessions"))
    for s in sessions:
        if s["SpecialSession"] or int(s["Year"][:4]) < 2011:  # noqa: PLR2004
            continue
        url = f"https://sdlegislature.gov/api/SessionMembers/Session/{s['SessionId']}"
        rows = [
            (
                "upper" if m["MemberType"] == "S" else "lower",
                m["District"].lstrip("0"),
                surname(m["LastName"]),
            )
            for m in json.loads(fetch(url))
        ]
        yield f"{s['Year'][:4]}-02-01", url, rows


def or_sessions():
    # every session key, so a member who left or joined mid-biennium is in one of them
    api = "https://api.oregonlegislature.gov/odata/odataservice.svc/"
    for s in json.loads(fetch(api + "LegislativeSessions?$format=json"))["value"]:
        # an interim key lists the members at some later date, not the session's own
        if s["BeginDate"][:4] < "2011" or s["SessionKey"][4] == "I":
            continue
        query = urllib.parse.quote(f"SessionKey eq '{s['SessionKey']}'")
        url = f"{api}Legislators?$filter={query}&$format=json"
        rows = [
            (
                "upper" if m["Chamber"] == "S" else "lower",
                m["DistrictNumber"],
                surname(m["LastName"]),
            )
            for m in json.loads(fetch(url))["value"]
        ]
        yield s["BeginDate"][:10], url, rows


def nd_sessions():
    for year in range(2011, dt.date.today().year + 1, 2):
        n = 62 + (year - 2011) // 2
        url = f"https://ndlegis.gov/assembly/{n}-{year}/regular/members/members-by-district"
        rx = (
            r'member-chamber">(\w+)</div>\s*<div class="strong member-name">([^<]+)'
            r'</div>.*?class="district">\s*District (\w+)'
        )
        rows = [
            ("upper" if c == "Senator" else "lower", d, surname(html.unescape(name)))
            for c, name, d in re.findall(rx, fetch(url), re.S)
        ]
        # replacements are listed too; the assembly's terms start in December
        yield f"{year}-02-01..{year + 1}-11-01", url, rows


def me_sessions():
    # House members-by-district from the 128th Legislature (Dec 2016) on
    for n in range(128, 128 + (dt.date.today().year - 2017) // 2 + 1):
        url = (
            "https://legislature.maine.gov/house/house/Documents/History"
            f"?Legislature={n}"
        )
        year = 2017 + 2 * (n - 128)
        # replacements are listed too; a Legislature's terms start in December
        yield f"{year}-02-01..{year + 1}-11-01", url, parse_me_house(fetch(url))


# state: (chambers covered, sessions). A session is (the day its roster is true on, or
# first..last for a roster of everyone who served in that period; its url; its rows)
SOURCES = {
    "nh": ({"lower"}, nh_sessions),
    "ar": (LEGISLATIVE, ar_sessions),
    "ak": (LEGISLATIVE, ak_sessions),
    "wv": (LEGISLATIVE, wv_sessions),
    "md": (LEGISLATIVE, md_sessions),
    "vt": (LEGISLATIVE, vt_sessions),
    "sd": (LEGISLATIVE, sd_sessions),
    "or": (LEGISLATIVE, or_sessions),
    "nd": (LEGISLATIVE, nd_sessions),
    "me": ({"lower"}, me_sessions),
}
_rosters = {}


def rosters(state):
    if state not in _rosters:
        _rosters[state] = list(SOURCES[state][1]())
    return _rosters[state]


def covers(role, day):
    """Whether the role is in a roster of `day`, or of `first..last` for a roster of
    everyone who served at any time in that period."""
    start, end = str(role.get("start_date") or ""), str(role.get("end_date") or "")
    first, _, last = day.partition("..")
    return bool(start) and start <= (last or first) and (not end or first < end)


def same_district(a, b):
    """'Essex-Orleans' and 'Essex Orleans' are the same district."""
    return a.replace("-", " ").casefold() == b.replace("-", " ").casefold()


def judge(role, who, rows):
    """(verdict, districts) for a role in one roster; who is the person's surnames."""
    chamber = role["type"]
    district = str(role.get("district"))
    there = {d for c, d, s in rows if c == chamber and s in who}
    if any(same_district(district, d) for d in there):
        return "roster-ok", district
    if there:
        return "ROSTER-MISMATCH", "/".join(sorted(there))
    return "roster-absent", ""


def check(path, person, role):
    state = path.split("/")[1]
    if role.get("type") not in LEGISLATIVE:
        return
    label = f"{role['type']} {role.get('district')}"
    head = (path, person.get("name"), label)
    if state not in SOURCES or role["type"] not in SOURCES[state][0]:
        yield (*head, "", "no-roster", "", "")
        return
    # every surname the record knows, for a name change (Bagnall -> Bagnall Tudball)
    names = [person.get("family_name"), person.get("name")]
    names += [o.get("name") for o in person.get("other_names") or []]
    who = {surname(n.split(",")[0] if "," in n else n) for n in names if n}
    for day, url, rows in rosters(state):
        if rows and covers(role, day):
            yield (*head, day, *judge(role, who, rows), url)


def self_test():
    assert surname("Timothy Lang, Sr., r") == "lang"
    assert surname("Juliet Harvey-Bolia") == "bolia"
    assert surname("John O\u2019Day") == "oday"
    org = """
                                   BELKNAP COUNTY (18)
Dist. No. 1 (1)    Tom Ploszaj, r
Dist. No. 2 (4)    Harry Bean, r; Jonathan Mackie, r
                   Norm Silber, r
2                               2 DECEMBER 2020 HOUSE RECORD
                                           CARROL COUNTY
Dist.No.2 (3)   Karen Umberger, r
"""
    assert parse_nh_org_day(org) == [
        ("lower", "Belknap 1", "ploszaj"),
        ("lower", "Belknap 2", "bean"),
        ("lower", "Belknap 2", "mackie"),
        ("lower", "Belknap 2", "silber"),
        ("lower", "Carroll 2", "umberger"),
    ]
    assert parse_nh_sponsors("(Gilman, Rock. 18; Steven Smith, Sull. 11;") == [
        ("lower", "Rockingham 18", "gilman"),
        ("lower", "Sullivan 11", "smith"),
    ]
    ar = (
        'Representative <a href="/Legislators/Detail?member=Berry&amp;dd=1">Stan Berry'
        '</a></div><div><span class="screenreader">Chamber:</span>\n House </div>'
        '<span class="screenreader">District:</span>\n  68\n</div>'
    )
    assert parse_ar(ar) == [("lower", "68", "berry")]
    ak = (
        '<a href="x">Senator Wielechowski        </nobr></a></td>\n'
        "<TD align=center>H </TD><TD>Democrat"
    )
    assert parse_ak(ak) == [("upper", "H", "wielechowski")]
    ak = '<a href="x">Senator Stevens G      </nobr></a></td>\n<TD align=center>R </TD>'
    assert parse_ak(ak) == [("upper", "R", "stevens")]
    rows = [("lower", "68", "berry"), ("lower", "44", "cooper")]
    role = {"type": "lower", "district": "68"}
    assert judge(role, {"berry"}, rows) == ("roster-ok", "68")
    mismatch = judge({**role, "district": "44"}, {"berry"}, rows)
    assert mismatch == ("ROSTER-MISMATCH", "68")
    assert judge(role, {"story"}, rows) == ("roster-absent", "")
    assert same_district("Essex-Orleans", "Essex Orleans")
    me = (
        "<span>District 11 - Assistant Majority Leader - Ryan Fecteau (D - Biddeford)"
        "</span><span>District 102 -  - Abigail Griffin (R - Levant)</span>"
    )
    assert parse_me_house(me) == [
        ("lower", "11", "fecteau"),
        ("lower", "102", "griffin"),
    ]
    assert covers({"start_date": "2019-01-14", "end_date": "2023-01-08"}, "2021-02-01")
    ended = {"start_date": "2019-01-14", "end_date": "2021-01-10"}
    assert not covers(ended, "2021-02-01")
    late = {
        "start_date": "2022-09-05",
        "end_date": "2023-01-03",
    }  # a mid-term appointee
    assert covers(late, "2021-02-01..2022-12-31")
    assert not covers(late, "2021-02-01")
    assert not covers(ended, "2021-02-01..2023-01-01")
    assert not covers({"end_date": "2021-01-10"}, "2019-02-01")  # no start: unjudgeable
    print("self-test ok")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("base", nargs="?")
    parser.add_argument("scope", nargs="*")
    parser.add_argument("--all", action="store_true", help="every role in scope")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    out = sys.stdout
    for kind, old_path, new_path in changed_files(
        args.base, args.scope, args.all and bool(args.scope)
    ):
        if new_path is None:
            continue
        person = load(None, new_path)
        old = load(args.base, old_path) if old_path and kind != "unchanged" else {}
        for role in person.get("roles") or []:
            if args.all or role not in (old.get("roles") or []):
                for row in check(new_path, person, role):
                    out.write("\t".join(str(v) for v in row) + "\n")


if __name__ == "__main__":
    main()
