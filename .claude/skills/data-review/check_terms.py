#!/usr/bin/env python3
"""Check role start/end dates against the legal term rules in term-rules.yml.

    uv run python .claude/skills/data-review/check_terms.py BASE [SCOPE ...] [--all]
    uv run python .claude/skills/data-review/check_terms.py --self-test

Checks the roles the working tree adds or edits relative to BASE (--all: every role in
scope). For each date it computes the rule's date for nearby election years and reports
the closest one. Tab-separated output: file, person, role, field, value, verdict,
expected, rule. Verdicts:

  ok           the legal rule's date
  repo-conv    the repo's documented convention (`repo:` in the table), not the legal
               date
  MISMATCH     within 21 days of a rule date but not on it: a wrong date, or a mid-term
               appointment that happens to land near one; check the source
  off-cycle    far from any rule date: a special election, appointment, resignation or
               death; verify against that person's own source
  placeholder  a YYYY-12-31 / YYYY-01-01 date the rule doesn't produce
  departure    an end_date with no later term of the same seat, not on a rule date: a
               death, resignation or removal; verify the vacancy date. `expected` is the
               term end, in case the person actually served the full term
  appointed    office is appointed in this state; verify against a confirmation record
  no-rule      no verified rule for this state/office, or a listed-dates rule whose
               list doesn't reach this date: research it and add it to the table
  overlap      a changed role overlaps another role of the same type (one person
               can't hold two such seats at once); `expected` is the other role
  seat-collision        a changed role's seat is also held by another person for 60+
               days of its span, in a chamber openstates metadata says is
               single-member (others, and `multi_member_until` periods, aren't
               checked). One of the records is wrong; `expected` is the other file
               and role
  seat-collision-other  as above, but the other record also holds another role over
               that span, so it is the likely wrong one: report it as existing data
  merged-terms one role now spans two or more separate terms of the same seat that
               BASE recorded as separate roles (BLOCKER; `value` is "N terms -> 1
               role"). Deleting a duplicate or an aggregate role that overlapped others
               is not a merge

Deleted roles (BASE has them, the working tree doesn't) get one row each, with the
role's dates in `value` and the surviving role that still records that service in
`expected` (prefixed with its file when it is in a likely duplicate person file):

  deleted-dup     a surviving role of the same seat covers the deleted span: a
                  duplicate was removed
  deleted-corrupt end_date before start_date: only end_date can be real, and a
                  surviving role still covers it
  deleted-precise like deleted-corrupt, but the survivor ends on a 12-31/01-01
                  placeholder where the deleted end was a real date: move the date
                  onto the survivor (after sourcing it) instead of discarding it
  deleted-inside  like deleted-corrupt, but the deleted end falls inside the survivor,
                  not at its end: the survivor may merge two terms and the deleted end
                  be the real boundary
  deleted-drops   like deleted-dup or deleted-corrupt, but the deleted role carries a
                  field the survivor lacks (end_reason, title...; `expected` names
                  them): move it onto the survivor instead of discarding it
  deleted-odd-end like deleted-precise or deleted-inside, but the deleted end_date is
                  neither a term-start date nor the day before one: an invented date
                  or a mid-term departure, so research it before keeping it
  deleted-other-seat no surviving role of the same seat covers the deleted span, but
                  one of the same chamber in another district does: a duplicate
                  filed under another district name (often the post-redistricting
                  one), so check which district the roster gives for those years
  deleted-LOST    no surviving role covers the deleted service: the change erases a
                  term unless a source shows it never happened (BLOCKER until sourced)
"""

import argparse
import calendar
import datetime as dt
import functools
import re
import sys
from pathlib import Path

import yaml
from extract_claims import changed_files, is_person, load, pair
from openstates import metadata

RULES = Path(__file__).with_name("term-rules.yml")
DOW: dict[str, int] = {d.lower(): i for i, d in enumerate(calendar.day_abbr)}
MON: dict[str, int] = {calendar.month_abbr[i].lower(): i for i in range(1, 13)}
ORD = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
LEGISLATIVE = {"upper", "lower", "legislature"}
NEAR = 21  # days: closer than this to a rule date but not on it = MISMATCH
NOVEMBER = 11
YEAR = 366  # days: a placeholder end further than this off is a merged role, not noise
SHARED = 60  # days: a seat shared for less than this is a handover, not a collision
LIST_WINDOW = 400  # days: a listed date further than this from a role date isn't judged


def nth_weekday(year, month, dow, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(dow - first.weekday()) % 7 + 7 * (n - 1))


def to_date(value):
    """A role date; a month- or year-only value reads as its first day."""
    value = str(value)
    return dt.date.fromisoformat(value + "-01" * (2 - value.count("-")))


def election(year):
    """General election: Tuesday after the first Monday in November."""
    return nth_weekday(year, NOVEMBER, DOW["mon"], 1) + dt.timedelta(days=1)


def anchor(text, ey):
    """Date for an anchor phrase, given the election year ey."""
    if text == "election":
        return election(ey)
    if m := re.fullmatch(r"(\d)(?:st|nd|rd|th) (\w{3}) of (\w{3})", text):
        month = MON[m[3]]
        return nth_weekday(ey + (month < NOVEMBER), month, DOW[m[2]], int(m[1]))
    if m := re.fullmatch(r"(\w{3}) (\d+)", text):
        month = MON[m[1]]
        return dt.date(ey + (month < NOVEMBER), month, int(m[2]))
    raise ValueError(f"unparseable rule anchor: {text!r}")  # noqa: TRY003


def rule_date(rule, ey):
    """Term start for an election held in year ey; None when the rule isn't a date."""
    rule = rule.lower().strip()
    if rule in ("oath", "certification", "varies"):
        return None
    if rule == "day after election":
        return election(ey) + dt.timedelta(days=1)
    if m := re.fullmatch(r"(\d+) days after election", rule):
        return election(ey) + dt.timedelta(days=int(m[1]))
    if m := re.fullmatch(r"(\w{3}) after (.+)", rule):
        base = anchor(m[2], ey)
        return base + dt.timedelta(days=(DOW[m[1]] - base.weekday() - 1) % 7 + 1)
    return anchor(rule, ey)


def nearest(rule, day):
    if isinstance(rule, list):  # explicit dates, e.g. each session's convening day
        dates = [dt.date.fromisoformat(str(d)) for d in rule]
        dates = [d for d in dates if abs((d - day).days) < LIST_WINDOW]
    else:
        dates = [
            d for ey in range(day.year - 2, day.year + 2) if (d := rule_date(rule, ey))
        ]
    return min(dates, key=lambda d: abs((d - day).days), default=None)


def rule_for(rules, state, role_type):
    """Return (entry, kind) where kind is 'rule', 'appointed' or None."""
    st = rules.get(state) or {}
    if role_type in LEGISLATIVE:
        leg = st.get("legislature") or {}
        kind = "rule" if leg.get("start") else None
        return {**leg, **(leg.get(role_type) or {})}, kind
    ex = st.get("executive") or {}
    if role_type in (ex.get("appointed") or []):
        return ex, "appointed"
    office = (ex.get("offices") or {}).get(role_type)
    entry = {**ex, "previous": None, **office} if office else ex
    return entry, "rule" if entry.get("start") else None


def in_effect(entry, day):
    """The rule version in force on `day`.

    A `previous:` version whose `until` is later than `day` wins.
    """
    for old in sorted(entry.get("previous") or [], key=lambda o: str(o["until"])):
        if day < dt.date.fromisoformat(str(old["until"])):
            return {**entry, "repo": None, **old}
    return entry


def verdict(entry, value, departure=False):  # noqa: PLR0911
    """`departure`: an end_date with no later term of the same seat."""
    day = to_date(value)
    entry = in_effect(entry, day)
    for key, name in (("start", "ok"), ("repo", "repo-conv")):
        if entry.get(key) and nearest(entry[key], day) == day:
            return name, ""
    expected = nearest(entry["start"], day)
    if len(str(value)) < len("YYYY-MM-DD"):
        return "partial", expected.isoformat() if expected else ""
    if departure and (day.month, day.day) not in ((12, 31), (1, 1)):
        return "departure", expected.isoformat() if expected else ""
    if expected is None and isinstance(entry["start"], list):
        return "no-rule", ""  # the list doesn't reach this date
    if expected is None:
        return "off-cycle", ""
    if abs((expected - day).days) < NEAR:
        return "MISMATCH", expected.isoformat()
    if (day.month, day.day) in ((12, 31), (1, 1)):
        return "placeholder", ""
    return "off-cycle", ""


def label(role):
    return " ".join(str(role.get(k)) for k in ("type", "district") if role.get(k))


def seat(role):
    return role.get("type"), str(role.get("district") or ""), role.get("jurisdiction")


def span(role, pad=0):
    start = to_date(role["start_date"]) - dt.timedelta(days=pad)
    end = role.get("end_date")
    end = to_date(end) + dt.timedelta(days=pad) if end else dt.date.max
    return start, end


def overlaps(a, b):
    (a0, a1), (b0, b1) = span(a), span(b)
    return a0 < b1 and b0 < a1


def overlap(role, roles):
    """Other roles of the same type and jurisdiction whose span overlaps `role`."""
    return [
        r
        for r in roles
        if r is not role
        and r.get("start_date")
        and role.get("start_date")
        and (r.get("type"), r.get("jurisdiction"))
        == (role.get("type"), role.get("jurisdiction"))
        and overlaps(r, role)
    ]


def days_shared(a, b):
    """Days two roles overlap; a role without start_date runs from the beginning."""
    lo = [
        to_date(r["start_date"]) if r.get("start_date") else dt.date.min for r in (a, b)
    ]
    hi = [to_date(r["end_date"]) if r.get("end_date") else dt.date.max for r in (a, b)]
    return (min(hi) - max(lo)).days


@functools.cache
def seat_holders(state):
    """{seat: [(path, role)]} for every dated role in the state's person files."""
    index = {}
    for path in sorted(Path("data", state).glob("*/*.yml")):
        if is_person(str(path)):
            for role in load(None, str(path)).get("roles") or []:
                if role.get("start_date"):
                    index.setdefault(seat(role), []).append((str(path), role))
    return index


def num_seats(rules, state, role):
    """1 when the role's chamber elects one member per district, else None (unknown).

    openstates metadata has today's map only, so a chamber with any multi-member
    district today (NH, MD, VT...), or with `multi_member_until` in the rules table
    later than the role's end (WV before 2022), isn't checked.
    """
    leg = (rules.get(state) or {}).get("legislature") or {}
    until = leg.get("multi_member_until")
    end = role.get("end_date")
    if until and (not end or to_date(end) <= to_date(until)):
        return None
    try:
        chamber = getattr(metadata.lookup(abbr=state), role.get("type") or "", None)
    except KeyError:
        return None
    districts = chamber.districts if chamber else []
    if not districts or any(d.num_seats != 1 for d in districts):
        return None
    return 1 if str(role.get("district")) in {d.name for d in districts} else None


def collisions(path, role, holders, seats):
    """Other people's roles holding `role`'s seat for SHARED+ days of its span.

    Empty unless they and `role` outnumber `seats`. Placeholder-dated roles are
    skipped: their spans are guesses.
    """
    if not role.get("start_date") or seats is None:
        return []
    found = [
        (p, r)
        for p, r in holders
        if p != path
        and not placeholder(r["start_date"])
        and not placeholder(r.get("end_date"))
        and days_shared(role, r) >= SHARED
    ]
    return found if len({p for p, _ in found}) >= seats else []


def double_booked(role, roles):
    """Whether another of the person's roles (any type) shares SHARED+ days with it."""
    return any(r != role and days_shared(role, r) >= SHARED for r in roles)


def merged_terms(kind, old, new):
    """Roles that now span two or more separate terms of one seat (terms combined).

    "Separate" means BASE had them as roles of that seat overlapping no other role,
    so deleting a duplicate or an aggregate role (one that overlapped others) is not
    a merge.
    A deleted file (duplicate merge) has no new version, so it never counts.
    """
    if kind not in ("edited", "moved"):
        return []
    old_roles = [r for r in old.get("roles") or [] if r.get("start_date")]
    separate = [
        r
        for r in old_roles
        if not any(
            o is not r and seat(o) == seat(r) and overlaps(o, r) for o in old_roles
        )
    ]
    found = []
    for role in new.get("roles") or []:
        if not role.get("start_date") or role in old_roles:
            continue
        lo, hi = span(role, pad=NEAR)
        inside = [
            r
            for r in separate
            if seat(r) == seat(role) and lo <= span(r)[0] and span(r)[1] <= hi
        ]
        if len(inside) > 1:
            found.append((role.get("type"), f"{len(inside)} terms", "1 role"))
    return found


def deleted_roles(kind, old, new):
    """Roles BASE had that the working tree drops; an edited role pairs, not deletes."""
    if kind not in ("edited", "moved"):
        return []
    return [
        a
        for _, a, b in pair("roles", old.get("roles") or [], new.get("roles") or [])
        if b is None and isinstance(a, dict)
    ]


def names(person):
    """A record's normalized `name` and `given_name family_name`."""
    given, family, name = (
        " ".join(str(person.get(k) or "").casefold().split())
        for k in ("given_name", "family_name", "name")
    )
    return {n for n in (name, given and family and f"{given} {family}") if n}


def namesakes(path, person=None):
    """Other person files in the state with the same first initial and last name.

    in the filename, or the same `name` (or given + family name) in the record, which
    catches a nickname filed under the legal name (Anne- vs Pinny-Beebe-Center).
    """
    stem = Path(path).stem.split("-")[:-5]  # drop the UUID
    key = (stem[0][0].lower(), stem[-1].lower()) if stem else None
    want = names(person or {})
    found = []
    for other, words, other_names in state_names(path.split("/")[1]):
        if other == path:
            continue
        if (words and (words[0][0].lower(), words[-1].lower()) == key) or (
            want & other_names
        ):
            found.append(other)
    return sorted(found)


@functools.cache
def state_names(state):
    """(path, filename words, names()) for every file in the state, parsed once."""
    return [
        (str(other), other.stem.split("-")[:-5], names(load(None, str(other))))
        for other in Path("data", state).glob("*/*.yml")
    ]


def placeholder(value):
    return str(value)[5:] in ("12-31", "01-01")


def near_start(role, day):
    """Whether `day` is within NEAR days of `role` start: the previous term's end."""
    start = role.get("start_date")
    return bool(start) and abs((to_date(start) - day).days) < NEAR


def covers(role, day, pad=NEAR):
    """Whether `role` (start_date optional) includes `day`.

    Allows NEAR days before the start and `pad` days after the end.
    """
    start = role.get("start_date")
    end = role.get("end_date")
    lo = to_date(start) - dt.timedelta(days=NEAR) if start else dt.date.min
    hi = to_date(end) + dt.timedelta(days=pad) if end else dt.date.max
    return lo <= day <= hi


SEAT_KEYS = ("type", "district", "jurisdiction")


def on_boundary(rules, path, role):
    """Whether end_date is a term-start date or the day before one; None if no rule."""
    entry, kind = rule_for(rules, path.split("/")[1], role.get("type"))
    if kind != "rule" or "/place:" in str(role.get("jurisdiction")):
        return None
    day = to_date(role["end_date"])
    entry = in_effect(entry, day)
    found = None
    for key in ("start", "repo"):
        rule = entry.get(key)
        if not rule or (
            isinstance(rule, str)
            and rule.lower() in ("oath", "certification", "varies")
        ):
            continue
        near = nearest(rule, day + dt.timedelta(days=1))
        found = found or near in (day, day + dt.timedelta(days=1))
    return found


def judge_deleted(rules, path, role, survivors):
    """deleted_verdict, with an end date that is no term boundary called out."""
    result, covered = deleted_verdict(role, survivors)
    if result in ("deleted-precise", "deleted-inside") and (
        on_boundary(rules, path, role) is False
    ):
        result = "deleted-odd-end"
    return result, covered


def role_span(role):
    """`type district start..end`, how a covering role is shown in `expected`."""
    name = " ".join(str(role.get(k) or "") for k in ("type", "district", "start_date"))
    return f"{name}..{role.get('end_date') or ''}"


def deleted_verdict(role, survivors):
    """(verdict, covering role) for a deleted role; survivors = [(file, role), ...]."""
    start, end = role.get("start_date"), role.get("end_date")
    corrupt = start and end and to_date(end) < to_date(start)
    days = [to_date(end)] if corrupt else [to_date(d) for d in (start, end) if d]
    for where, other in survivors:
        if corrupt:
            same = other.get("jurisdiction") == role.get("jurisdiction")
        else:
            same = seat(other) == seat(role)
        # a 12-31/01-01 placeholder only says which year: it may run up to a year
        # past the survivor's end, never before its start
        pads = [YEAR if placeholder(d) else NEAR for d in days]
        if same and days and all(map(covers, [other] * len(days), days, pads)):
            name = role_span(other)
            result = "deleted-corrupt" if corrupt else "deleted-dup"
            if corrupt and (kept := other.get("end_date")):
                gap = abs((to_date(kept) - days[0]).days)
                if gap and gap < YEAR and placeholder(kept) and not placeholder(end):
                    result = "deleted-precise"
                elif gap >= NEAR and not near_start(other, days[0]):
                    result = "deleted-inside"
            elif corrupt and not near_start(other, days[0]):
                result = "deleted-inside"
            # fields beyond the seat and dates that only the deleted role records
            lost = sorted(
                k
                for k in role
                if k not in ("start_date", "end_date", *SEAT_KEYS)
                and other.get(k) is None
            )
            if lost and result in ("deleted-dup", "deleted-corrupt"):
                result, name = "deleted-drops", f"{name} lacks {', '.join(lost)}"
            return result, (f"{where}: {name}" if where else name)
    # the same chamber under another district still records the service
    for where, other in survivors:
        if (
            not corrupt
            and days
            and other.get("type") == role.get("type")
            and other.get("jurisdiction") == role.get("jurisdiction")
            and all(covers(other, d) for d in days)
        ):
            name = role_span(other)
            return "deleted-other-seat", (f"{where}: {name}" if where else name)
    return "deleted-LOST", ""


def check(rules, path, person, role, roles=()):
    state = path.split("/")[1]
    entry, kind = rule_for(rules, state, role.get("type"))
    if "/place:" in str(role.get("jurisdiction")):  # municipal: the table has no rule
        entry, kind = {}, None
    label = " ".join(str(role.get(k)) for k in ("type", "district") if role.get(k))
    for field in ("start_date", "end_date"):
        if not role.get(field):
            continue
        value = str(role[field])
        rule = (
            in_effect(entry, to_date(value)).get("start", "") if kind == "rule" else ""
        )
        # a `repo:` convention is still checkable when the legal rule isn't a date
        fixed = (
            isinstance(rule, str)
            and rule.lower() in ("oath", "certification", "varies")
            and not in_effect(entry, to_date(value)).get("repo")
        )
        if kind is None:
            result, expected = "no-rule", ""
        elif kind == "appointed":
            result, expected = "appointed", ""
        elif fixed:
            result, expected = "off-cycle", ""
        else:
            day = to_date(value)
            departure = field == "end_date" and not any(
                seat(r) == seat(role)
                and r.get("start_date")
                and abs((to_date(r["start_date"]) - day).days) < NEAR
                for r in roles
            )
            result, expected = verdict(entry, value, departure)
        if isinstance(rule, list):
            rule = "listed dates"
        yield path, person, label, field, value, result, expected, rule


def self_test():  # noqa: PLR0915
    cases = {  # rule, election year -> date the repo already records
        ("Wed after 1st Mon of Jan", 2022): "2023-01-04",  # CT
        ("Mon after 2nd Tue of Jan", 2022): "2023-01-16",  # AL statewide
        ("Tue after 1st Mon of Jan", 2022): "2023-01-03",  # FL statewide
        ("Mon after Jan 1", 2022): "2023-01-02",  # CA statewide
        ("1st Mon of Dec", 2022): "2022-12-05",  # CA legislature, AK statewide
        ("2nd Mon of Jan", 2022): "2023-01-09",  # GA legislature
        ("2nd Tue of Jan", 2022): "2023-01-10",  # CO statewide
        ("day after election", 2022): "2022-11-09",  # AL legislature
        ("election", 2022): "2022-11-08",  # FL legislature
        ("Jan 3", 2024): "2025-01-03",  # US Congress
        ("15 days after election", 2018): "2018-11-21",  # OK legislature
        ("Tue after Dec 6", 2023): "2023-12-12",  # KY governor, odd-year election
        ("Mon after election", 2022): "2022-11-14",  # SC legislature
    }
    for (rule, ey), want in cases.items():
        got = rule_date(rule, ey).isoformat()
        assert got == want, f"{rule} {ey}: {got} != {want}"
    entry = {"start": "Wed after 1st Mon of Jan"}
    assert verdict(entry, "2023-01-04") == ("ok", "")
    assert verdict(entry, "2023-01-09") == ("MISMATCH", "2023-01-04")
    assert verdict(entry, "2023-06-19") == ("off-cycle", "")
    assert verdict(entry, "2020-12-31") == ("MISMATCH", "2021-01-06")
    assert verdict({"start": "Jan 20"}, "2019-06-30")[0] == "off-cycle"
    assert verdict(entry, "2023-01") == ("partial", "2023-01-04")
    mayor = {
        "type": "mayor",
        "jurisdiction": "ocd-jurisdiction/country:us/state:ca/place:chico/government",
        "start_date": "2024-12",
    }
    ca = {"ca": {"executive": {"start": "Mon after Jan 1"}}}
    assert next(check(ca, "data/ca/municipalities/x.yml", "X", mayor))[5] == "no-rule"
    az = {"az": {"legislature": {"start": "varies", "repo": "2nd Mon of Jan"}}}
    sen = {"type": "upper", "district": "27", "start_date": "2015-01-12"}
    assert next(check(az, "data/az/legislature/x.yml", "X", sen))[5] == "repo-conv"
    sen = {**sen, "start_date": "2015-06-01"}
    assert next(check(az, "data/az/legislature/x.yml", "X", sen))[5] == "off-cycle"
    del az["az"]["legislature"]["repo"]
    sen = {**sen, "start_date": "2015-01-12"}
    assert next(check(az, "data/az/legislature/x.yml", "X", sen))[5] == "off-cycle"
    listed = {"start": ["2023-01-09", "2025-01-08"]}
    assert verdict(listed, "2025-01-08") == ("ok", "")
    assert verdict(listed, "2025-01-14") == ("MISMATCH", "2025-01-08")
    assert verdict(listed, "2015-01-07") == ("no-rule", "")  # outside the list
    gov = {
        "type": "governor",
        "jurisdiction": "ocd-jurisdiction/country:us/state:de/government",
    }
    two = {
        "roles": [
            {**gov, "start_date": "2017-01-17", "end_date": "2021-01-19"},
            {**gov, "start_date": "2021-01-19", "end_date": "2025-01-21"},
        ]
    }
    one = {"roles": [{**gov, "start_date": "2017-01-17", "end_date": "2025-01-21"}]}
    assert merged_terms("edited", two, one) == [("governor", "2 terms", "1 role")]
    shifted = {"roles": [{**gov, "start_date": "2017-01-18", "end_date": "2025-01-21"}]}
    assert merged_terms("edited", two, shifted) == [("governor", "2 terms", "1 role")]
    rep = {
        "type": "lower",
        "district": "WA-9",
        "jurisdiction": "ocd-jurisdiction/country:us/government",
    }
    terms = [
        {**rep, "start_date": "2021-01-03", "end_date": "2023-01-03"},
        {**rep, "start_date": "2023-01-03", "end_date": "2025-01-03"},
    ]
    aggregate = {
        "roles": [{**rep, "start_date": "1997-01-03", "end_date": "2030-12-31"}, *terms]
    }
    assert (
        merged_terms("edited", aggregate, {"roles": terms}) == []
    )  # aggregate removed
    dup = {"roles": [*terms, {**terms[1], "end_date": "2025-01-02"}]}
    assert merged_terms("edited", dup, {"roles": terms}) == []  # near-duplicate removed
    retired = {
        "roles": [*two["roles"][:1], {**two["roles"][1], "end_reason": "term ended"}]
    }
    assert (
        merged_terms("moved", two, retired) == []
    )  # executive/ -> retired/, roles kept
    assert merged_terms("deleted", two, {}) == []  # duplicate record deleted
    assert merged_terms("edited", one, two) == []  # a split is not a merge
    jan3 = {"start": "Jan 3"}
    assert verdict(jan3, "2025-01-20", departure=True) == (
        "departure",
        "2025-01-03",
    )  # resigned
    assert verdict(jan3, "2025-01-20") == (
        "MISMATCH",
        "2025-01-03",
    )  # a later term starts
    assert verdict(jan3, "2025-01-03", departure=True) == ("ok", "")
    assert (
        verdict(jan3, "2024-12-31", departure=True)[0] == "MISMATCH"
    )  # placeholder stays
    changed = {
        "start": "2nd Mon of Jan",
        "previous": [{"start": "1st Mon of Jan", "until": "2015-01-01"}],
    }
    assert verdict(changed, "2013-01-07") == ("ok", "")  # old law
    assert verdict(changed, "2023-01-09") == ("ok", "")  # new law
    assert verdict(changed, "2023-01-02")[0] == "MISMATCH"

    nh = "ocd-jurisdiction/country:us/state:nh/government"
    cur = {
        "type": "upper",
        "district": "16",
        "jurisdiction": nh,
        "start_date": "2022-12-07",
    }
    house = {
        "type": "lower",
        "district": "H 7",
        "jurisdiction": nh,
        "end_date": "2018-12-05",
    }
    bad = {**cur, "end_date": "2018-12-04"}  # copied start, real end
    assert deleted_verdict(bad, [(None, cur), (None, house)])[0] == "deleted-corrupt"
    assert deleted_verdict(bad, [(None, cur)])[0] == "deleted-LOST"
    dup_file = [("data/nh/retired/x.yml", {**house, "end_date": "2018-12-31"})]
    assert deleted_verdict(bad, dup_file) == (
        "deleted-precise",
        "data/nh/retired/x.yml: lower H 7 ..2018-12-31",
    )
    term = {**house, "start_date": "2016-12-07"}
    assert deleted_verdict(term, [(None, {**term, "end_date": "2018-12-04"})])[0] == (
        "deleted-dup"
    )
    eight = {**term, "district": "H 8"}
    assert deleted_verdict(term, [(None, cur), (None, eight)]) == (
        "deleted-other-seat",
        "lower H 8 2016-12-07..2018-12-05",
    )  # the same chamber under another district name still records the term
    assert (
        deleted_verdict(term, [(None, {**term, "type": "upper", "district": "8"})])[0]
        == "deleted-LOST"
    )  # another chamber doesn't
    old = {"roles": [cur, bad]}
    assert deleted_roles("edited", old, {"roles": [cur]}) == [bad]
    moved = {"roles": [cur, {**bad, "start_date": "2016-12-07"}]}
    assert deleted_roles("edited", old, moved) == []  # an edit, not a deletion
    # a bogus copy of the current role deleted while an older role of another
    # district is edited: the edit pairs with its own district, not the copy
    ten = {**house, "district": "H 10", "end_date": "2018-12-31"}
    gone = deleted_roles(
        "edited",
        {"roles": [cur, bad, ten]},
        {"roles": [cur, {**ten, "end_date": "2018-12-04"}]},
    )
    assert gone == [bad]
    assert deleted_roles("deleted", old, {}) == []  # a duplicate file deleted
    nh_rules = {"nh": {"legislature": {"start": "1st Wed of Dec"}}}
    path = "data/nh/legislature/x.yml"
    for end, want in (
        ("2016-12-06", True),
        ("2016-12-07", True),
        ("2016-06-01", False),
    ):
        assert on_boundary(nh_rules, path, {**cur, "end_date": end}) is want, end
    assert on_boundary({}, path, {**cur, "end_date": "2016-06-01"}) is None  # no rule
    late = {**house, "end_date": "2018-12-05"}
    assert deleted_verdict(bad, [(None, late)])[0] == "deleted-corrupt"  # a day apart
    far = [(None, {**house, "start_date": "2014-12-03", "end_date": "2020-12-31"})]
    assert deleted_verdict(bad, far)[0] == "deleted-inside"  # 2 years off: merged
    merged = {**house, "start_date": "2014-12-03", "end_date": "2022-12-07"}
    assert deleted_verdict(bad, [(None, merged)])[0] == "deleted-inside"
    nxt = {**house, "start_date": "2018-12-05", "end_date": "2020-12-02"}
    assert deleted_verdict(bad, [(None, nxt)])[0] == "deleted-corrupt"  # next term
    rep = {"type": "lower", "district": "1", "jurisdiction": nh}
    t1 = {**rep, "start_date": "2020-12-02", "end_date": "2022-12-07"}
    t2 = {**rep, "start_date": "2022-12-07"}
    assert overlap(t1, [t1, t2]) == []  # end == next start is not an overlap
    t0 = {**rep, "district": "2", "start_date": "2018-12-05", "end_date": "2022-12-07"}
    assert overlap(t1, [t0, t1, t2]) == [t0]
    pinny = {"name": "Pinny Beebe-Center", "given_name": "Anne"}
    assert names(pinny) == {"pinny beebe-center"}

    sen = {"type": "upper", "district": "H", "jurisdiction": "j"}
    pr_role = {**sen, "start_date": "2015-01-20", "end_date": "2023-01-16"}
    claman = {**sen, "start_date": "2015-01-20", "end_date": "2023-01-16"}
    house = {"type": "lower", "district": "21", "end_date": "2023-01-11"}
    holders = [("b.yml", claman)]
    assert collisions("a.yml", pr_role, holders, 1) == holders
    assert collisions("a.yml", pr_role, holders, 2) == []  # two-seat district
    assert collisions("a.yml", pr_role, holders, None) == []  # seats unknown
    handover = {**sen, "start_date": "2023-01-01", "end_date": "2027-01-01"}
    assert collisions("a.yml", pr_role, [("b.yml", handover)], 1) == []
    guess = {**sen, "start_date": "2015-01-01", "end_date": "2018-12-31"}
    assert collisions("a.yml", pr_role, [("b.yml", guess)], 1) == []  # placeholder
    wv = {"wv": {"legislature": {"multi_member_until": "2022-12-01"}}}
    old_wv = {"type": "lower", "district": "48", "end_date": "2022-11-30"}
    assert num_seats(wv, "wv", old_wv) is None  # multi-member then
    assert num_seats({}, "ar", {"type": "lower", "district": "49"}) == 1
    assert num_seats({}, "nh", {"type": "lower", "district": "Rockingham 6"}) is None
    undated = {"type": "lower", "district": "3", "end_date": "2018-12-31"}
    kept = {**undated, "start_date": "2016-12-07", "end_date": "2018-12-04"}
    assert deleted_verdict(undated, [(None, kept)])[0] == "deleted-dup"  # placeholder
    corrupt = {"type": "upper", "start_date": "2021-04-06", "end_date": "2021-01-01"}
    later = {"type": "upper", "start_date": "2021-04-06"}  # starts after the end
    assert deleted_verdict(corrupt, [(None, later)])[0] == "deleted-LOST"
    resigned = {**undated, "end_date": "2018-12-04", "end_reason": "Resigned"}
    assert deleted_verdict(resigned, [(None, kept)]) == (
        "deleted-drops",
        "lower 3 2016-12-07..2018-12-04 lacks end_reason",
    )
    carried = {**kept, "end_reason": "Resigned"}
    assert deleted_verdict(resigned, [(None, carried)])[0] == "deleted-dup"
    assert double_booked(claman, [claman, house])  # undated House role underneath
    assert not double_booked(claman, [claman, {**house, "end_date": "2015-01-20"}])

    def walk(node, where):  # every rule in the table must parse
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("start", "repo") and isinstance(value, str):
                    try:
                        rule_date(value, 2022)
                    except (ValueError, KeyError) as e:
                        raise AssertionError(f"{where}.{key}: {e}") from e  # noqa: TRY003
                walk(value, f"{where}.{key}")
        elif isinstance(node, list):  # `previous:` versions
            for i, item in enumerate(node):
                walk(item, f"{where}[{i}]")

    walk(yaml.safe_load(RULES.read_text()), "term-rules")
    print("self-test ok")


def write(out, row):
    out.write(
        "\t".join(" ".join(str(v).split()) for v in row) + "\n"
    )  # data can hold tabs


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

    rules = yaml.safe_load(RULES.read_text())
    out = sys.stdout
    for kind, old_path, new_path in changed_files(
        args.base, args.scope, args.all and bool(args.scope)
    ):
        if new_path is None:
            continue
        person = load(None, new_path)
        old = (
            person
            if kind == "unchanged"
            else load(args.base, old_path)
            if old_path
            else {}
        )
        old_roles = old.get("roles") or []
        old_dates = {
            (r.get("type"), f, str(r.get(f)))
            for r in old_roles
            for f in ("start_date", "end_date")
        }
        for role_type, before, after in merged_terms(kind, old, person):
            row = (
                new_path,
                person.get("name"),
                role_type,
                "roles",
                f"{before} -> {after}",
                "merged-terms",
                "",
                "",
            )
            write(out, row)
        gone = deleted_roles(kind, old, person)
        survivors = [(None, r) for r in person.get("roles") or []]
        if gone:
            survivors += [
                (other, r)
                for other in namesakes(new_path, person)
                for r in load(None, other).get("roles") or []
            ]
        for role in gone:
            result, covered = judge_deleted(rules, new_path, role, survivors)
            value = f"{role.get('start_date') or ''}..{role.get('end_date') or ''}"
            write(
                out,
                (
                    new_path,
                    person.get("name"),
                    label(role),
                    "roles",
                    value,
                    result,
                    covered,
                    "",
                ),
            )
        for role in person.get("roles") or []:
            if args.all or role not in old_roles:
                for other in overlap(role, person.get("roles") or []):
                    span_ = f"{role.get('start_date')}..{role.get('end_date') or ''}"
                    found = (
                        f"{label(other)} {other.get('start_date')}.."
                        f"{other.get('end_date') or ''}"
                    )
                    row = (
                        new_path,
                        person.get("name"),
                        label(role),
                        "roles",
                        span_,
                        "overlap",
                        found,
                        "",
                    )
                    write(out, row)
                state = new_path.split("/")[1]
                for other, theirs in collisions(
                    new_path,
                    role,
                    seat_holders(state).get(seat(role), []),
                    num_seats(rules, state, role),
                ):
                    result = (
                        "seat-collision-other"
                        if double_booked(theirs, load(None, other).get("roles") or [])
                        else "seat-collision"
                    )
                    found = (
                        f"{other} {theirs.get('start_date')}.."
                        f"{theirs.get('end_date') or ''}"
                    )
                    span_ = f"{role.get('start_date')}..{role.get('end_date') or ''}"
                    row = (new_path, person.get("name"), label(role), "roles")
                    write(out, (*row, span_, result, found, ""))
                for row in check(
                    rules, new_path, person.get("name"), role, person.get("roles") or []
                ):
                    # an edit to another field (district) leaves the dates as they were
                    if args.all or (role.get("type"), row[3], row[4]) not in old_dates:
                        write(out, row)


if __name__ == "__main__":
    main()
