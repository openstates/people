#!/usr/bin/env python3
"""Find dead URLs in data/ YAML files, either in a PR's diff or across the repo.

"Dead" is deliberately narrow: the server answered 404/410, or the host's domain
no longer exists (NXDOMAIN). Anything else - 403, 429, 5xx, timeouts, TLS errors,
LinkedIn's 999 - is "unknown" and never treated as dead, because many government
sites block scripts (gov.ca.gov answers curl with 403 but works in a browser), and
GitHub's runner IPs get blocked more often still. A blocked request is not a
broken link.

Two modes:

  --changed-files F... [--base-ref SHA]
      PR mode. Checks only URLs (links, image, sources) that the change added or
      changed relative to the base revision; untouched files and lines are never
      requested. Exits 1 if any new URL is dead; unknowns are warnings.

  --prune [PATH...]
      Sweep mode. Checks every `links` URL and `image` in the given files/dirs
      (default: data/) and removes the dead ones in place. `sources` are kept:
      they record where data came from, which stays true after the page dies.
      Use --cache to make a long sweep resumable.

Rate limiting: URLs are grouped by host, each host is visited by one worker at a
time with a pause between requests, and many hosts run in parallel. A 429 backs
off and retries. Every dead result is re-checked once at the end of the run
before being acted on, and a host whose own homepage also 404s is treated as
blocking us rather than dead.
"""

from __future__ import annotations

import argparse
import json
import socket
import threading
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit

import requests
import yaml
from _git_base import read_at_base

USER_AGENT = (
    "Mozilla/5.0 (compatible; openstates-people-linkcheck; "
    "+https://github.com/openstates/people)"
)
# These answer every scripted request the same way (login wall, 403, or 999),
# so a request tells us nothing; their links are always kept.
SKIP_HOSTS = (
    "linkedin.com",
    "votesmart.org",
    "facebook.com",
    "twitter.com",
    "x.com",
    "instagram.com",
)
DEAD_CODES = {404, 410}
TOO_MANY_REQUESTS = 429
RATE_LIMIT_TRIES = 3
CACHE_SAVE_EVERY = 30  # seconds
UNREACHABLE = {
    "unknown:ConnectTimeout",
    "unknown:ReadTimeout",
    "unknown:ConnectionError",
}
UNREACHABLE_LIMIT = 5  # consecutive failures before giving up on a host
HOST_DELAY = 0.5  # seconds between requests to the same host
TIMEOUT = (10, 20)  # connect, read
WORKERS = 64
PR_URL_CAP = 300

_local = threading.local()


def _session() -> requests.Session:
    if not hasattr(_local, "session"):
        _local.session = requests.Session()
        _local.session.headers["User-Agent"] = USER_AGENT
    return _local.session


def host_of(url: str) -> str:
    return (urlsplit(url).hostname or "").lower()


def skipped(url: str) -> bool:
    host = host_of(url)
    return not host or any(host == h or host.endswith("." + h) for h in SKIP_HOSTS)


@cache
def nxdomain(host: str) -> bool:
    try:
        socket.getaddrinfo(host, None)
    except socket.gaierror as e:
        return e.errno == socket.EAI_NONAME
    return False


def check_url(url: str) -> str:
    """Return "ok", "dead:<why>", or "unknown:<why>"."""
    if nxdomain(host_of(url)):
        return "dead:nxdomain"
    for attempt in range(RATE_LIMIT_TRIES):
        try:
            # GET, not HEAD: some servers 404 a HEAD for pages that exist.
            # stream=True so only headers are read, never the body.
            with _session().get(url, timeout=TIMEOUT, stream=True) as resp:
                code = resp.status_code
                retry_after = resp.headers.get("Retry-After", "")
        except requests.RequestException as e:
            return f"unknown:{type(e).__name__}"
        if code == TOO_MANY_REQUESTS and attempt < RATE_LIMIT_TRIES - 1:
            time.sleep(min(int(retry_after) if retry_after.isdigit() else 30, 120))
            continue
        if code in DEAD_CODES:
            return f"dead:{code}"
        return "ok" if resp.ok else f"unknown:{code}"
    return "unknown:429"


def _check_host(urls: list[str]) -> dict[str, str]:
    results = {}
    unreachable = 0
    for i, url in enumerate(urls):
        # A host that keeps timing out or refusing would cost ~20s per URL and
        # end up all-unknown anyway; stop asking it.
        if unreachable >= UNREACHABLE_LIMIT:
            results[url] = "unknown:host-unreachable"
            continue
        if i:
            time.sleep(HOST_DELAY)
        results[url] = check_url(url)
        failed = results[url] in UNREACHABLE
        unreachable = unreachable + 1 if failed else 0
    return results


def check_urls(urls: set[str], cache_path: Path | None = None) -> dict[str, str]:
    results: dict[str, str] = {}
    if cache_path and cache_path.exists():
        results = json.loads(cache_path.read_text())
    by_host: dict[str, list[str]] = defaultdict(list)
    for url in sorted(urls - results.keys()):
        if skipped(url):
            results[url] = "unknown:skipped-host"
        else:
            by_host[host_of(url)].append(url)
    # Biggest hosts first: they bound the total run time.
    hosts = sorted(by_host, key=lambda h: -len(by_host[h]))
    print(f"checking {sum(map(len, by_host.values()))} URLs on {len(hosts)} hosts")

    lock = threading.Lock()
    last_save = [time.monotonic()]

    def run(host: str) -> None:
        checked = _check_host(by_host[host])
        with lock:
            results.update(checked)
            if cache_path and time.monotonic() - last_save[0] > CACHE_SAVE_EVERY:
                cache_path.write_text(json.dumps(results))
                last_save[0] = time.monotonic()

    with ThreadPoolExecutor(WORKERS) as pool:
        list(pool.map(run, hosts))

    # Re-check every dead result once, minutes later for a big run, so a brief
    # outage or deploy doesn't delete a working link.
    dead = {u for u in urls if results.get(u, "").startswith("dead:")}
    if dead:
        nxdomain.cache_clear()
        by_host = defaultdict(list)
        for url in sorted(dead):
            by_host[host_of(url)].append(url)
        with ThreadPoolExecutor(WORKERS) as pool:
            for host, rechecked in zip(
                by_host, pool.map(_check_host, by_host.values()), strict=True
            ):
                results.update(rechecked)
                still_dead = [u for u in rechecked if results[u].startswith("dead:4")]
                if not still_dead:
                    continue
                # A homepage that also 404s means the host 404s everything we
                # send it (bot filtering), not that each page is gone.
                root = f"{urlsplit(by_host[host][0]).scheme}://{host}/"
                if check_url(root).startswith("dead:4"):
                    for url in still_dead:
                        results[url] = "unknown:host-404s-homepage"
    if cache_path:
        cache_path.write_text(json.dumps(results))
    return results


def load(text: str | None) -> dict:
    return (yaml.safe_load(text) if text else None) or {}


def record_urls(record: dict, include_sources: bool) -> set[str]:
    if not isinstance(record, dict):  # e.g. municipalities.yml is a list
        return set()
    keys = ("links", "sources") if include_sources else ("links",)
    urls = {
        item["url"]
        for key in keys
        for item in record.get(key) or []
        if isinstance(item, dict) and item.get("url")
    }
    if isinstance(record.get("image"), str) and record["image"]:
        urls.add(record["image"])
    return urls


def remove_dead(text: str, dead: set[str]) -> str | None:
    """Drop dead top-level `links` items and `image` from a YAML file's text.

    Edits lines rather than re-dumping the file so the diff shows only the
    removed entries. Returns None if the result doesn't parse to exactly the
    original minus those entries, so a surprising layout is skipped, not mangled.
    """
    original = load(text)
    out: list[str] = []
    lines = text.splitlines(keepends=True)
    in_links = False
    i = 0
    while i < len(lines):
        line = lines[i]
        if line[:1] not in (" ", "-", "\n", ""):
            in_links = line.startswith("links:")
            if line.startswith("image:"):
                end = i + 1  # long values wrap onto indented lines
                while end < len(lines) and lines[end].startswith("  "):
                    end += 1
                if load("".join(lines[i:end])).get("image") in dead:
                    i = end
                    continue
        if in_links and line.startswith("- "):
            end = i + 1
            while end < len(lines) and lines[end].startswith("  "):
                end += 1
            item = (yaml.safe_load("".join(lines[i:end])) or [None])[0]
            if isinstance(item, dict) and item.get("url") in dead:
                i = end
                continue
        out.append(line)
        i += 1
    # A `links:` header left with no items would load as null; drop it.
    out = [
        line
        for j, line in enumerate(out)
        if not (
            line == "links:\n"
            and (j + 1 == len(out) or not out[j + 1].startswith("- "))
        )
    ]
    result = "".join(out)

    expected = dict(original)
    if expected.get("image") in dead:
        del expected["image"]
    if isinstance(expected.get("links"), list):
        kept = [
            item
            for item in expected["links"]
            if not (isinstance(item, dict) and item.get("url") in dead)
        ]
        if kept:
            expected["links"] = kept
        else:
            del expected["links"]
    return result if load(result) == expected else None


def yaml_files(paths: list[str]) -> list[Path]:
    files: list[Path] = []
    for p in map(Path, paths):
        files.extend(sorted(p.rglob("*.yml")) if p.is_dir() else [p])
    return [f for f in files if f.suffix == ".yml"]


def prune(paths: list[str], cache_path: Path | None) -> int:
    files = yaml_files(paths or ["data"])
    texts = {f: f.read_text() for f in files}
    urls_by_file = {
        f: record_urls(load(t), include_sources=False) for f, t in texts.items()
    }
    results = check_urls(set().union(*urls_by_file.values()), cache_path)

    removed = skipped_files = 0
    for f, urls in urls_by_file.items():
        dead = {u for u in urls if results[u].startswith("dead:")}
        if not dead:
            continue
        new_text = remove_dead(texts[f], dead)
        if new_text is None:
            skipped_files += 1
            print(f"SKIPPED (unexpected layout) {f}: {sorted(dead)}")
            continue
        f.write_text(new_text)
        removed += len(dead)
        for url in sorted(dead):
            print(f"removed {results[url]} {f}: {url}")

    counts: dict[str, int] = defaultdict(int)
    for status in results.values():
        counts[status.split(":")[0]] += 1
    print(f"\n{dict(counts)}; removed {removed} URLs; skipped {skipped_files} files")
    return 0


def check_changed(changed: list[str], base_ref: str | None) -> int:
    new_urls: dict[str, set[Path]] = defaultdict(set)
    for f in yaml_files(changed):
        if f.parts[:1] != ("data",) or not f.exists():
            continue
        head = record_urls(load(f.read_text()), include_sources=True)
        base = (
            record_urls(load(read_at_base(base_ref, f)), include_sources=True)
            if base_ref
            else set()
        )
        for url in head - base:
            new_urls[url].add(f)
    if not new_urls:
        print("No new or changed URLs to check")
        return 0

    urls = sorted(new_urls)
    if len(urls) > PR_URL_CAP:
        print(
            f"::warning::{len(urls)} new URLs; checking the first {PR_URL_CAP}. "
            "Run check_links.py --prune locally for the rest."
        )
        urls = urls[:PR_URL_CAP]
    results = check_urls(set(urls))

    failed = False
    for url in urls:
        status = results[url]
        for f in sorted(new_urls[url]):
            if status.startswith("dead:"):
                failed = True
                print(f"::error file={f}::dead URL ({status}): {url}")
            elif status.startswith("unknown:") and status != "unknown:skipped-host":
                print(f"::warning file={f}::could not verify URL ({status}): {url}")
    print(f"checked {len(urls)} new URLs")
    return 1 if failed else 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--changed-files", nargs="*", help="PR mode: changed files")
    mode.add_argument("--prune", nargs="*", help="sweep mode: files/dirs to prune")
    parser.add_argument(
        "--base-ref", help="PR mode: only check URLs new since this ref"
    )
    parser.add_argument("--cache", type=Path, help="sweep mode: resumable results file")
    args = parser.parse_args()
    if args.prune is not None:
        return prune(args.prune, args.cache)
    return check_changed(args.changed_files, args.base_ref)


if __name__ == "__main__":
    raise SystemExit(main())
