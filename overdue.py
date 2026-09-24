#!/usr/bin/env python
"""List traps in a Trap.NZ project that haven't been checked for more than N days."""

import argparse
import sys

from rich.console import Console
from rich.table import Table

import trapnz


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", help="project name (case-insensitive partial match)")
    parser.add_argument("-l", "--line", help="only show this line colour, e.g. Purple")
    parser.add_argument("-d", "--days", type=float, default=15,
                        help="show traps not checked for more than this many days (default 15)")
    parser.add_argument("--csv", default=trapnz.DEFAULT_CSV, help="trap line assignments CSV")
    args = parser.parse_args()

    console = Console()
    try:
        projects = trapnz.match_projects(args.project)
        traps = trapnz.get_traps(projects, args.csv)
    except trapnz.TrapNZError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    if args.line:
        traps = [t for t in traps if t.line.lower() == args.line.lower()]
    overdue = [t for t in traps if (t.days_overdue() or 0) > args.days]
    overdue.sort(key=lambda t: (-t.days_overdue(), t.code))

    title = f"{', '.join(projects)}{' – ' + args.line if args.line else ''}"
    if not overdue:
        console.print(f"No traps in {title} overdue by more than {args.days:g} days.")
        return 0

    try:
        trapnz.fill_last_status(overdue)
    except trapnz.TrapNZError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1

    table = Table(title=f"{title}: {len(overdue)} trap(s) not checked for > {args.days:g} days")
    table.add_column("Trap ID", justify="right")
    table.add_column("Code")
    if len(projects) > 1:
        table.add_column("Project")
    table.add_column("Line")
    table.add_column("Last checked")
    table.add_column("Days", justify="right")
    table.add_column("Last status")
    for t in overdue:
        row = [str(t.nid), t.code]
        if len(projects) > 1:
            row.append(t.project)
        last = trapnz.fmt_date(t.last_checked)
        row += [t.line, last, f"{t.days_overdue():.0f}", t.last_status or "-"]
        table.add_row(*row)
    console.print(table)
    return 0


if __name__ == "__main__":
    sys.exit(main())
