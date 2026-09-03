#!/usr/bin/env python3
"""Cross-check current governor records against two independent sources.

Deterministic fact check: pulls current officeholder name/party from
Wikidata's structured statements and from Wikipedia's "List of current
United States governors" table, then diffs both against our active
governor YAML. No AI involved in the comparison, so results are exact-match
diffs a human can verify quickly, not judgment calls.

Both external sources are themselves manually maintained and can lag
reality (e.g. after an election before someone updates the page). A single
source disagreeing with us is weak evidence — it might just be stale. We
only flag a state when BOTH independent sources disagree with us, which is
much less likely to be simultaneous staleness.
"""

from __future__ import annotations

import argparse
import datetime
import json
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

_WIKIDATA_ENDPOINT = "https://query.wikidata.org/sparql"
_WIKIPEDIA_ENDPOINT = "https://en.wikipedia.org/w/api.php"
_USER_AGENT = (
    "openstates-people-governor-check/1.0 (https://github.com/openstates/people)"
)

_SPARQL_QUERY = """
SELECT ?stateLabel ?personLabel ?partyLabel ?start ?end WHERE {
  ?state wdt:P31 wd:Q35657 .
  ?state p:P6 ?stmt .
  ?stmt ps:P6 ?person .
  OPTIONAL { ?stmt pq:P580 ?start }
  OPTIONAL { ?stmt pq:P582 ?end }
  OPTIONAL { ?person wdt:P102 ?party }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
}
"""

_STATE_NAME_TO_ABBR = {
    "Alabama": "al",
    "Alaska": "ak",
    "Arizona": "az",
    "Arkansas": "ar",
    "California": "ca",
    "Colorado": "co",
    "Connecticut": "ct",
    "Delaware": "de",
    "Florida": "fl",
    "Georgia": "ga",
    "Hawaii": "hi",
    "Idaho": "id",
    "Illinois": "il",
    "Indiana": "in",
    "Iowa": "ia",
    "Kansas": "ks",
    "Kentucky": "ky",
    "Louisiana": "la",
    "Maine": "me",
    "Maryland": "md",
    "Massachusetts": "ma",
    "Michigan": "mi",
    "Minnesota": "mn",
    "Mississippi": "ms",
    "Missouri": "mo",
    "Montana": "mt",
    "Nebraska": "ne",
    "Nevada": "nv",
    "New Hampshire": "nh",
    "New Jersey": "nj",
    "New Mexico": "nm",
    "New York": "ny",
    "North Carolina": "nc",
    "North Dakota": "nd",
    "Ohio": "oh",
    "Oklahoma": "ok",
    "Oregon": "or",
    "Pennsylvania": "pa",
    "Rhode Island": "ri",
    "South Carolina": "sc",
    "South Dakota": "sd",
    "Tennessee": "tn",
    "Texas": "tx",
    "Utah": "ut",
    "Vermont": "vt",
    "Virginia": "va",
    "Washington": "wa",
    "West Virginia": "wv",
    "Wisconsin": "wi",
    "Wyoming": "wy",
}

_PARTY_LABEL_TO_OURS = {
    "Democratic Party": "Democratic",
    "Republican Party": "Republican",
    # Minnesota's Democratic Party affiliate goes by this name on our side.
    "Democratic-Farmer-Labor Party": "Democratic-Farmer-Labor",
}
_PARTY_EQUIVALENTS = {
    ("Democratic", "Democratic-Farmer-Labor"),
    ("Democratic-Farmer-Labor", "Democratic"),
    ("Democratic", "Democratic–Farmer–Labor"),  # noqa: RUF001
    ("Democratic–Farmer–Labor", "Democratic"),  # noqa: RUF001
}


def fetch_url(url: str, accept: str) -> bytes:
    request = urllib.request.Request(  # noqa: S310
        url, headers={"Accept": accept, "User-Agent": _USER_AGENT}
    )
    with urllib.request.urlopen(request, timeout=60) as response:  # noqa: S310
        return response.read()


def names_conflict(a: str, b: str) -> bool:
    """True only when neither name is a subsequence-ignoring-punctuation
    variant of the other (handles "Dan"/"Daniel", "JB"/"J. B.", middle
    initials, etc.) — a real mismatch means genuinely different people."""

    def tokens(name: str) -> set[str]:
        return {t.strip(".").lower() for t in name.split()}

    a_tokens, b_tokens = tokens(a), tokens(b)
    shorter, longer = (
        (a_tokens, b_tokens) if len(a_tokens) <= len(b_tokens) else (b_tokens, a_tokens)
    )
    return not all(
        any(
            long_t.startswith(short_t) or short_t.startswith(long_t)
            for long_t in longer
        )
        for short_t in shorter
    )


def parties_conflict(a: str | None, b: str | None) -> bool:
    if a == b:
        return False
    return (a, b) not in _PARTY_EQUIVALENTS


def fetch_wikidata_governors() -> dict[str, dict]:
    """Return {abbr: {"name": ..., "party": ...}} for the officeholder
    statement with the latest start date per state."""
    url = f"{_WIKIDATA_ENDPOINT}?{urllib.parse.urlencode({'query': _SPARQL_QUERY})}"
    data = json.loads(fetch_url(url, "application/sparql-results+json"))

    latest: dict[str, dict] = {}
    starts: dict[str, str] = {}
    for row in data["results"]["bindings"]:
        abbr = _STATE_NAME_TO_ABBR.get(row["stateLabel"]["value"])
        if not abbr:
            continue
        start = row.get("start", {}).get("value", "")
        if abbr not in starts or start > starts[abbr]:
            starts[abbr] = start
            party_label = row.get("partyLabel", {}).get("value")
            latest[abbr] = {
                "name": row["personLabel"]["value"],
                "party": _PARTY_LABEL_TO_OURS.get(party_label, party_label),
            }
    return latest


_NAME_RE = re.compile(r"\{\{sortname\|([^|}]+)\|([^|}]+)|\[\[([^\]|]+)\]\]")
_PARTY_RE = re.compile(
    r'style="background-color:\{\{party color\|[^}]+\}\};"\s*\|\s*\n\|\s*'
    r"\[\[[^\]|]*\|?([^\]]+)\]\]"
)


def fetch_wikipedia_governors() -> dict[str, dict]:
    """Return {abbr: {"name": ..., "party": ...}} parsed from Wikipedia's
    "List of current United States governors" table (section 1: state
    governors)."""
    params = {
        "action": "parse",
        "page": "List of current United States governors",
        "prop": "wikitext",
        "format": "json",
        "section": "1",
    }
    url = f"{_WIKIPEDIA_ENDPOINT}?{urllib.parse.urlencode(params)}"
    data = json.loads(fetch_url(url, "application/json"))
    wikitext = data["parse"]["wikitext"]["*"]

    table_start = wikitext.find("{|")
    table_end = wikitext.find("|}", table_start)
    rows = wikitext[table_start:table_end].split("\n|-")[1:]

    result: dict[str, dict] = {}
    for row in rows:
        state_match = re.search(r"\[\[Governor of ([^|\]]+)", row)
        if not state_match:
            continue
        abbr = _STATE_NAME_TO_ABBR.get(state_match.group(1).strip())
        if not abbr:
            continue

        row_header = row.split('! scope="row"', 1)
        name_match = _NAME_RE.search(row_header[1]) if len(row_header) > 1 else None
        if not name_match:
            continue
        if name_match.group(3):
            name = name_match.group(3).strip()
        else:
            name = f"{name_match.group(1).strip()} {name_match.group(2).strip()}"

        party_match = _PARTY_RE.search(row)
        party = party_match.group(1).strip() if party_match else None

        result[abbr] = {"name": name, "party": party}
    return result


def load_our_governors(
    data_dir: Path, abbrs: list[str], as_of: datetime.date
) -> dict[str, dict]:
    """Return {abbr: {"name": ..., "party": ...}} for the governor whose term
    covers `as_of`."""
    today = as_of.isoformat()
    ours: dict[str, dict] = {}
    for abbr in abbrs:
        exec_dir = data_dir / abbr / "executive"
        if not exec_dir.exists():
            continue
        for path in sorted(exec_dir.glob("*.yml")):
            person = yaml.safe_load(path.read_text())
            for role in person.get("roles", []):
                if role.get("type") != "governor":
                    continue
                start = role.get("start_date", "")
                end = role.get("end_date", "9999-12-31")
                if str(start) <= today <= str(end):
                    party = (person.get("party") or [{}])[0].get("name")
                    ours[abbr] = {
                        "name": person.get("name"),
                        "party": party,
                        "file": path.name,
                    }
    return ours


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    parser.add_argument(
        "--date", type=datetime.date.fromisoformat, default=datetime.date.today()
    )
    args = parser.parse_args()

    abbrs = sorted(_STATE_NAME_TO_ABBR.values())
    wikidata = fetch_wikidata_governors()
    wikipedia = fetch_wikipedia_governors()
    ours = load_our_governors(args.data_dir, abbrs, args.date)

    mismatches = []
    for abbr in abbrs:
        mine = ours.get(abbr)
        sources = {"Wikidata": wikidata.get(abbr), "Wikipedia": wikipedia.get(abbr)}
        available = {name: src for name, src in sources.items() if src is not None}
        if not available:
            continue

        if mine is None:
            names = ", ".join(
                f"{name}={src['name']} ({src['party']})"
                for name, src in available.items()
            )
            mismatches.append(f"{abbr}: no active governor on file; {names}")
            continue

        name_conflicts = {
            name: src
            for name, src in available.items()
            if names_conflict(mine["name"], src["name"])
        }
        if len(name_conflicts) == len(available) and available:
            names = ", ".join(
                f"{name}={src['name']!r}" for name, src in name_conflicts.items()
            )
            mismatches.append(
                f"{abbr}: name mismatch — ours={mine['name']!r} "
                f"({mine['file']}) vs {names}"
            )
            continue

        party_conflicts = {
            name: src
            for name, src in available.items()
            if parties_conflict(mine["party"], src["party"])
        }
        if len(party_conflicts) == len(available) and available:
            parties = ", ".join(
                f"{name}={src['party']!r}" for name, src in party_conflicts.items()
            )
            mismatches.append(
                f"{abbr}: party mismatch for {mine['name']} — "
                f"ours={mine['party']!r} vs {parties}"
            )

    if mismatches:
        print(
            f"Found {len(mismatches)} governor fact mismatch(es) confirmed by all "
            "available sources:"
        )
        for m in mismatches:
            print(f"  - {m}")
        return 1

    print(
        f"All {len(ours)} governors on file match Wikidata and Wikipedia's "
        "current officeholder data."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
