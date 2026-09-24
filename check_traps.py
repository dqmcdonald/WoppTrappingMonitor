#!/usr/bin/env python
"""Daily check: send ntfy alerts for traps not checked for N, 2N, 3N ... days.

Each trap is notified once when it reaches N days overdue, again at 2N, and so
on; the count resets when the trap is next checked. Alerts are grouped into a
single message per line topic (trapnz_secrets.NTFY_TOPICS).
"""

import argparse
import json
import os
import sys
from collections import defaultdict

import requests

import trapnz
import trapnz_secrets

DEFAULT_STATE = os.path.join(trapnz.HERE, "state.json")


def load_state(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(path, state):
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, path)


def send_ntfy(topic, title, body):
    server = getattr(trapnz_secrets, "NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    r = requests.post(f"{server}/{topic}", data=body.encode("utf-8"),
                      headers={"Title": title.encode("utf-8"), "Tags": "warning"},
                      timeout=30)
    r.raise_for_status()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-n", "--days", type=float, default=15,
                        help="notification interval in days (default 15)")
    parser.add_argument("--state", default=DEFAULT_STATE, help="state file (default state.json)")
    parser.add_argument("--csv", default=trapnz.DEFAULT_CSV, help="trap line assignments CSV")
    parser.add_argument("--dry-run", action="store_true",
                        help="print notifications instead of sending; don't update state")
    args = parser.parse_args()

    try:
        traps = trapnz.get_traps(trapnz_secrets.PROJECT_IDS, args.csv)
    except trapnz.TrapNZError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    state = load_state(args.state)
    new_state = {}
    pending = defaultdict(list)   # (project, line) -> [(trap, level)]
    for t in traps:
        key = str(t.nid)
        last = t.last_checked.isoformat() if t.last_checked else None
        prev = state.get(key, {})
        notified = prev.get("notified_level", 0) if prev.get("last_record_date") == last else 0
        new_state[key] = {"code": t.code, "last_record_date": last, "notified_level": notified}

        days = t.days_overdue()
        level = int(days // args.days) if days is not None else 0
        if level >= 1 and level > notified:
            pending[(t.project, t.line)].append((t, level))

    try:
        trapnz.fill_last_status([t for group in pending.values() for t, _ in group])
    except trapnz.TrapNZError as e:
        print(f"Warning: couldn't fetch last statuses: {e}", file=sys.stderr)

    errors = 0
    for (project, line), items in sorted(pending.items()):
        items.sort(key=lambda item: -item[0].days_overdue())
        topic = trapnz_secrets.NTFY_TOPICS.get(project, {}).get(line)
        title = f"{len(items)} trap(s) overdue – {project} {line}"
        body = "\n".join(
            f"{t.code}  last checked {trapnz.fmt_date(t.last_checked)}  "
            f"{t.days_overdue():.0f}d  {t.last_status or '-'}"
            for t, _ in items
        )
        if topic is None:
            print(f"Error: no NTFY topic for {project!r} line {line!r}", file=sys.stderr)
            errors += 1
            continue
        if args.dry_run:
            print(f"[{topic}] {title}\n{body}\n")
            continue
        try:
            send_ntfy(topic, title, body)
        except requests.RequestException as e:
            print(f"Error: sending to {topic} failed: {e}", file=sys.stderr)
            errors += 1
            continue
        print(f"Sent to {topic}: {title}")
        for t, level in items:
            new_state[str(t.nid)]["notified_level"] = level

    if not pending:
        print("No new overdue traps to notify.")
    if not args.dry_run:
        save_state(args.state, new_state)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
