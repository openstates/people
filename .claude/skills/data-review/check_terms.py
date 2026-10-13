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
  no-rule      no verified rule for this state/office: research it and add it
  merged-terms one role now spans two or more separate terms of the same seat that
               BASE recorded as separate roles (BLOCKER; `value` is "N terms -> 1
               role"). Deleting a duplicate or an aggregate role that overlapped others
               is not a merge
"""

import argparse
import calendar
import datetime as dt
import re
import sys
from pathlib import Path

import yaml
from extract_claims import changed_files, load

RULES = Path(__file__).with_name("term-rules.yml")
DOW: dict[str, int] = {d.lower(): i for i, d in enumerate(calendar.day_abbr)}
MON: dict[str, int] = {calendar.month_abbr[i].lower(): i for i in range(1, 13)}
ORD = {"1st": 1, "2nd": 2, "3rd": 3, "4th": 4}
LEGISLATIVE = {"upper", "lower", "legislature"}
NEAR = 21  # days: closer than this to a rule date but not on it = MISMATCH
NOVEMBER = 11
LIST_WINDOW = 400  # days: a listed date further than this from a role date isn't judged


def nth_weekday(year, month, dow, n):
    first = dt.date(year, month, 1)
    return first + dt.timedelta(days=(dow - first.weekday()) % 7 + 7 * (n - 1))


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


def verdict(entry, value, departure=False):
    """`departure`: an end_date with no later term of the same seat."""
    day = dt.date.fromisoformat(str(value))
    entry = in_effect(entry, day)
    for key, name in (("start", "ok"), ("repo", "repo-conv")):
        if entry.get(key) and nearest(entry[key], day) == day:
            return name, ""
    expected = nearest(entry["start"], day)
    if departure and (day.month, day.day) not in ((12, 31), (1, 1)):
        return "departure", expected.isoformat() if expected else ""
    if expected is None:
        return "off-cycle", ""
    if abs((expected - day).days) < NEAR:
        return "MISMATCH", expected.isoformat()
    if (day.month, day.day) in ((12, 31), (1, 1)):
        return "placeholder", ""
    return "off-cycle", ""


def seat(role):
    return role.get("type"), str(role.get("district") or ""), role.get("jurisdiction")


def span(role, pad=0):
    start = dt.date.fromisoformat(str(role["start_date"])) - dt.timedelta(days=pad)
    end = role.get("end_date")
    end = (
        dt.date.fromisoformat(str(end)) + dt.timedelta(days=pad) if end else dt.date.max
    )
    return start, end


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

    def overlaps(a, b):
        (a0, a1), (b0, b1) = span(a), span(b)
        return a0 < b1 and b0 < a1

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


def check(rules, path, person, role, roles=()):
    state = path.split("/")[1]
    entry, kind = rule_for(rules, state, role.get("type"))
    label = " ".join(str(role.get(k)) for k in ("type", "district") if role.get(k))
    for field in ("start_date", "end_date"):
        if not role.get(field):
            continue
        value = str(role[field])
        rule = (
            in_effect(entry, dt.date.fromisoformat(value)).get("start", "")
            if kind == "rule"
            else ""
        )
        fixed = isinstance(rule, str) and rule.lower() in (
            "oath",
            "certification",
            "varies",
        )
        if kind is None:
            result, expected = "no-rule", ""
        elif kind == "appointed":
            result, expected = "appointed", ""
        elif fixed:
            result, expected = "off-cycle", ""
        else:
            day = dt.date.fromisoformat(value)
            departure = field == "end_date" and not any(
                seat(r) == seat(role)
                and r.get("start_date")
                and abs((dt.date.fromisoformat(str(r["start_date"])) - day).days) < NEAR
                for r in roles
            )
            result, expected = verdict(entry, value, departure)
        if isinstance(rule, list):
            rule = "listed dates"
        yield path, person, label, field, value, result, expected, rule


def self_test():
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
    listed = {"start": ["2023-01-09", "2025-01-08"]}
    assert verdict(listed, "2025-01-08") == ("ok", "")
    assert verdict(listed, "2025-01-14") == ("MISMATCH", "2025-01-08")
    assert verdict(listed, "2015-01-07") == ("off-cycle", "")  # outside the list
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

    def walk(node, where):  # every rule in the table must parse
        if isinstance(node, dict):
            for key, value in node.items():
                if key in ("start", "repo") and isinstance(value, str):
                    try:
                        rule_date(value, 2022)
                    except (ValueError, KeyError) as e:
                        raise AssertionError(f"{where}.{key}: {e}") from e  # noqa: TRY003
                walk(value, f"{where}.{key}")

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
        for role in person.get("roles") or []:
            if args.all or role not in old_roles:
                for row in check(
                    rules, new_path, person.get("name"), role, person.get("roles") or []
                ):
                    write(out, row)


if __name__ == "__main__":
    main()
