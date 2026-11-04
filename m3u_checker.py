#!/usr/bin/env python3
"""
m3u_checker.py - validate an M3U/M3U8 IPTV playlist and report dead streams.

Usage:
    python m3u_checker.py playlist.m3u
    python m3u_checker.py https://example.com/playlist.m3u --workers 20 --timeout 8
    python m3u_checker.py playlist.m3u --csv report.csv --alive alive.m3u

What it does:
    1. Reads the playlist from a local file or a URL.
    2. Parses every #EXTINF entry (name, group-title, tvg-id, tvg-logo, URL).
    3. Sends an HTTP request to each stream URL (HEAD first, GET on failure)
       using a thread pool, and records the status code and response time.
    4. Prints a summary, optionally writes a CSV report and a cleaned playlist
       that contains only the streams that answered.

No third-party packages are required (Python 3.8+, standard library only).
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional

USER_AGENT = "Mozilla/5.0 (compatible; m3u-checker/1.0; +https://github.com/smartvpro-tv/m3u-playlist-checker)"
ATTR_RE = re.compile(r'([\w-]+)="([^"]*)"')


@dataclass
class Entry:
    name: str
    url: str
    group: str = ""
    tvg_id: str = ""
    tvg_logo: str = ""
    extinf: str = ""
    status: Optional[int] = None
    ok: bool = False
    ms: int = 0
    error: str = ""
    extra: List[str] = field(default_factory=list)


def read_source(source: str, timeout: int) -> str:
    if source.startswith(("http://", "https://")):
        req = urllib.request.Request(source, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read().decode("utf-8", errors="replace")
    with open(source, "r", encoding="utf-8", errors="replace") as fh:
        return fh.read()


def parse_m3u(text: str) -> List[Entry]:
    entries: List[Entry] = []
    current: Optional[Entry] = None
    extra: List[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#EXTINF"):
            attrs = dict(ATTR_RE.findall(line))
            name = line.rsplit(",", 1)[1].strip() if "," in line else ""
            current = Entry(
                name=name,
                url="",
                group=attrs.get("group-title", ""),
                tvg_id=attrs.get("tvg-id", ""),
                tvg_logo=attrs.get("tvg-logo", ""),
                extinf=line,
            )
            extra = []
        elif line.startswith("#"):
            if current is not None and not line.startswith("#EXTM3U"):
                extra.append(line)  # e.g. #EXTVLCOPT lines
        else:
            if current is None:
                current = Entry(name=line, url="", extinf="#EXTINF:-1," + line)
            current.url = line
            current.extra = extra
            entries.append(current)
            current = None
            extra = []
    return entries


def check_url(url: str, timeout: int) -> tuple[Optional[int], bool, int, str]:
    start = time.monotonic()
    for method in ("HEAD", "GET"):
        try:
            req = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                status = resp.status
                if method == "GET":
                    resp.read(1024)  # read a small chunk to confirm data flows
                ms = int((time.monotonic() - start) * 1000)
                return status, 200 <= status < 400, ms, ""
        except urllib.error.HTTPError as exc:
            ms = int((time.monotonic() - start) * 1000)
            if method == "HEAD" and exc.code in (403, 405, 501):
                continue  # server rejects HEAD; retry with GET
            return exc.code, False, ms, f"HTTP {exc.code}"
        except Exception as exc:  # timeouts, DNS, connection refused, SSL
            if method == "HEAD":
                continue
            ms = int((time.monotonic() - start) * 1000)
            return None, False, ms, type(exc).__name__
    ms = int((time.monotonic() - start) * 1000)
    return None, False, ms, "unknown"


def run(entries: List[Entry], workers: int, timeout: int, quiet: bool) -> None:
    total = len(entries)
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(check_url, e.url, timeout): e for e in entries}
        for fut in as_completed(futures):
            entry = futures[fut]
            entry.status, entry.ok, entry.ms, entry.error = fut.result()
            done += 1
            if not quiet:
                mark = "OK " if entry.ok else "DEAD"
                code = entry.status if entry.status is not None else entry.error
                print(f"[{done}/{total}] {mark} {code:>8} {entry.ms:>6} ms  {entry.name}")


def write_csv(path: str, entries: List[Entry]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["name", "group", "tvg_id", "url", "ok", "status", "ms", "error"])
        for e in entries:
            writer.writerow([e.name, e.group, e.tvg_id, e.url, int(e.ok), e.status or "", e.ms, e.error])


def write_m3u(path: str, entries: List[Entry]) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("#EXTM3U\n")
        for e in entries:
            fh.write(e.extinf + "\n")
            for line in e.extra:
                fh.write(line + "\n")
            fh.write(e.url + "\n")


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an M3U IPTV playlist and report dead streams.")
    parser.add_argument("source", help="path or URL of the .m3u / .m3u8 playlist")
    parser.add_argument("--workers", type=int, default=10, help="parallel requests (default 10)")
    parser.add_argument("--timeout", type=int, default=10, help="seconds per request (default 10)")
    parser.add_argument("--csv", metavar="FILE", help="write a CSV report")
    parser.add_argument("--alive", metavar="FILE", help="write a playlist containing only working streams")
    parser.add_argument("--dead", metavar="FILE", help="write a playlist containing only dead streams")
    parser.add_argument("--group", metavar="NAME", help="only check entries whose group-title contains NAME")
    parser.add_argument("--quiet", action="store_true", help="print the summary only")
    args = parser.parse_args(argv)

    try:
        text = read_source(args.source, args.timeout)
    except Exception as exc:
        print(f"Could not read playlist: {exc}", file=sys.stderr)
        return 2

    entries = parse_m3u(text)
    if args.group:
        needle = args.group.lower()
        entries = [e for e in entries if needle in e.group.lower()]
    if not entries:
        print("No entries found. Is this a valid M3U file?", file=sys.stderr)
        return 1

    print(f"Checking {len(entries)} streams with {args.workers} workers, {args.timeout}s timeout...\n")
    started = time.monotonic()
    run(entries, args.workers, args.timeout, args.quiet)
    elapsed = time.monotonic() - started

    alive = [e for e in entries if e.ok]
    dead = [e for e in entries if not e.ok]
    print("\n" + "=" * 60)
    print(f"Total:   {len(entries)}")
    print(f"Working: {len(alive)}  ({len(alive) * 100 // len(entries)}%)")
    print(f"Dead:    {len(dead)}")
    print(f"Time:    {elapsed:.1f}s")

    if dead:
        groups: dict[str, int] = {}
        for e in dead:
            groups[e.group or "(no group)"] = groups.get(e.group or "(no group)", 0) + 1
        print("\nDead streams by group:")
        for g, n in sorted(groups.items(), key=lambda kv: -kv[1])[:15]:
            print(f"  {n:>5}  {g}")

    if args.csv:
        write_csv(args.csv, entries)
        print(f"\nCSV report written to {args.csv}")
    if args.alive:
        write_m3u(args.alive, alive)
        print(f"Working playlist written to {args.alive}")
    if args.dead:
        write_m3u(args.dead, dead)
        print(f"Dead playlist written to {args.dead}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
