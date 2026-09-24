# WOPP Trapping Monitor

Scripts to monitor trap checking across [Trap.NZ](https://trap.nz) projects:

- **`overdue.py`** – prints a table of traps that haven't been checked for more than N days.
- **`check_traps.py`** – designed to run daily; sends [ntfy](https://ntfy.sh) alerts for traps that are overdue, escalating at N, 2N, 3N… days.

Trap lines aren't always assigned in Trap.NZ, so each trap's line (colour) comes from a local `TrapLineAssignments.csv`.

## Setup

Requires Python 3.10+ with `requests` and `rich`:

```sh
pip install requests rich
```

### `trapnz_secrets.py` (not committed)

```python
TRAP_NZ_API_KEY = "your Trap.NZ WFS API key"

COASTAL = "Diamond Harbour Coastal"
STODDART = "Diamond Harbour Stoddart Point"

PROJECT_IDS = {COASTAL: 27388029, STODDART: 23404747}

# ntfy topic for each project / line colour
NTFY_TOPICS = {
    COASTAL: {"Purple": "...", "Pink": "...", "Green": "..."},
    STODDART: {"Pink": "...", "Purple": "..."},
}

NTFY_SERVER = "https://ntfy.sh"   # optional
```

### `TrapLineAssignments.csv` (not committed)

A CSV with at least the columns `trap nid`, `code` and `line`, e.g.

```
trap nid,code,trap type,...,line,line_colour,distance_m
28433140,DHD016,DOC 200,...,Green,#7BD148,0.39
```

Each active trap is looked up by its Trap.NZ nid first, and then by its code (so a trap that has been re-created in Trap.NZ with a new nid still matches). An active trap that can't be found either way is an error: the scripts list every unmapped trap and exit with status 1. Retired traps are ignored.

## Data source

The API key is a Trap.NZ **WFS** key, so data is read from the WFS feed
(`https://io.trap.nz/geo/trapnz-projects/wfs/<KEY>/default`, layers `my-projects-traps` and `my-projects-trap-records`). The newer `api2.trap.nz` REST API needs OAuth2 username/password credentials and isn't used.

## Usage

```sh
# Coastal traps not checked for more than 15 days (default)
python overdue.py coastal

# Stoddart Point, Pink line only, more than 10 days
python overdue.py stoddart -l pink -d 10
```

The project name is a case-insensitive partial match against the names in `PROJECT_IDS`.

```sh
# See what would be sent without sending or saving state
python check_traps.py --dry-run

# Normal daily run (N = 15)
python check_traps.py
python check_traps.py -n 20        # use a different interval
```

### How notifications escalate

For each trap, `check_traps.py` works out `level = floor(days since last check / N)`. It notifies when the level reaches 1 (N days), then again at 2 (2N days), 3 (3N days) and so on. The level is stored in `state.json` next to the script, and it resets as soon as a new check of the trap is recorded in Trap.NZ. A trap that has never been checked counts from its install date.

Each run sends at most **one message per line topic**, listing every trap on that line that reached a new level. State is only updated for messages that were sent successfully, so a failed send is retried on the next run.

On the very first run every trap that is already overdue gets reported.

## Scheduling

cron (daily at 7am):

```cron
0 7 * * * /Users/you/venvs/tf/bin/python /path/to/WoppTrappingMonitor/check_traps.py >> /path/to/WoppTrappingMonitor/check_traps.log 2>&1
```

Paths for the CSV and state file are resolved relative to the script, so the working directory doesn't matter.
