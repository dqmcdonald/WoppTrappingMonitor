#!/usr/bin/env python
"""Daily check: send ntfy alerts for lines with traps not checked for N, 2N, 3N ... days.

Each line (trapnz_secrets.NTFY_TOPICS) gets a single notification when its
longest-unchecked trap reaches N days, another at 2N, and so on. Each message
lists every trap on the line that is N+ days overdue. Once the line is checked
the count starts again.
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

    # Group overdue traps by line; a line's level is set by its longest-unchecked trap.
    lines = defaultdict(list)   # (project, line) -> [overdue traps]
    # Traps with no records have never been set, so they aren't overdue.
    for t in traps:
        if t.last_checked and t.days_overdue() >= args.days:
            lines[(t.project, t.line)].append(t)

    state = load_state(args.state)
    new_state = {}
    pending = {}
    for key in {(t.project, t.line) for t in traps}:
        state_key = f"{key[0]} | {key[1]}"
        overdue = lines.get(key, [])
        level = int(max(t.days_overdue() for t in overdue) // args.days) if overdue else 0
        # If the line has been (partly) checked since, its level drops; start counting from there.
        notified = min(state.get(state_key, {}).get("notified_level", 0), level)
        new_state[state_key] = {"notified_level": notified}
        if level >= 1 and level > notified:
            pending[key] = (overdue, level)

    errors = 0
    for (project, line), (overdue, level) in sorted(pending.items()):
        overdue.sort(key=lambda t: (-t.days_overdue(), t.code))
        topic = trapnz_secrets.NTFY_TOPICS.get(project, {}).get(line)
        oldest = overdue[0].days_overdue()
        title = f"{project} {line} line: {len(overdue)} trap(s) not checked for {args.days:g}+ days"
        body = "\n".join(
            f"{t.code}  last checked {trapnz.fmt_date(t.last_checked)}  {t.days_overdue():.0f}d"
            for t in overdue
        )
        if topic is None:
            print(f"Error: no NTFY topic for {project!r} line {line!r}", file=sys.stderr)
            errors += 1
            continue
        if args.dry_run:
            print(f"[{topic}] {title} (oldest {oldest:.0f}d, level {level})\n{body}\n")
            continue
        try:
            send_ntfy(topic, title, body)
        except requests.RequestException as e:
            print(f"Error: sending to {topic} failed: {e}", file=sys.stderr)
            errors += 1
            continue
        print(f"Sent to {topic}: {title}")
        new_state[f"{project} | {line}"]["notified_level"] = level

    if not pending:
        print("No lines need a new notification.")
    if not args.dry_run:
        save_state(args.state, new_state)
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
