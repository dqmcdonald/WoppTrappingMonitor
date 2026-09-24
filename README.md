# WOPP Trapping Monitor

Scripts to monitor trap checking across [Trap.NZ](https://trap.nz) projects:

- **`overdue.py`** – prints a table of traps that haven't been checked for more than N days.
- **`check_traps.py`** – designed to run daily; sends one [ntfy](https://ntfy.sh) alert per line when its traps are overdue, escalating at N, 2N, 3N… days.

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

Notifications are per **line** (one ntfy topic per project/line in `NTFY_TOPICS`). A line's level is `floor(days since its longest-unchecked trap was checked / N)`. The line gets a single notification when its level reaches 1 (N days), another at 2 (2N days), 3 (3N days) and so on. Each message lists every trap on the line that is N or more days overdue, with its last check date. Traps that have never been set (no records in Trap.NZ) are ignored.

The last notified level for each line is stored in `state.json` next to the script. When the line is checked, its level drops and counting starts again from there. State is only updated after a message is sent successfully, so a failed send is retried on the next run.

On the very first run every line that is already overdue gets one message.

## Scheduling

On macOS use launchd rather than cron. If the Mac is asleep at the scheduled time, cron skips the run, but launchd runs it as soon as the Mac wakes. Several missed days still produce only one run. Neither runs while the Mac is shut down.

Create `~/Library/LaunchAgents/nz.wopp.checktraps.plist` (daily at 7am; adjust the paths):

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>nz.wopp.checktraps</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/you/venvs/tf/bin/python</string>
        <string>/path/to/WoppTrappingMonitor/check_traps.py</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key><integer>7</integer>
        <key>Minute</key><integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>/path/to/WoppTrappingMonitor/check_traps.log</string>
    <key>StandardErrorPath</key>
    <string>/path/to/WoppTrappingMonitor/check_traps.log</string>
</dict>
</plist>
```

Then load it:

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/nz.wopp.checktraps.plist
```

### Useful commands

```sh
launchctl kickstart gui/$(id -u)/nz.wopp.checktraps        # run it now
cat /path/to/WoppTrappingMonitor/check_traps.log           # see what happened
launchctl print gui/$(id -u)/nz.wopp.checktraps | grep -E "state =|last exit"   # is it loaded, did the last run succeed
launchctl bootout gui/$(id -u)/nz.wopp.checktraps          # stop scheduling it
```

After editing the plist, run the `bootout` command and then the `bootstrap` command again to reload it.

A run right after waking may start before the network is back, so `check_traps.py` retries fetching from Trap.NZ (5 retries, 60 s apart by default; see `--retries` and `--retry-wait`). Each run writes a timestamp line to the log.

On Linux, cron works:

```cron
0 7 * * * /path/to/venv/bin/python /path/to/WoppTrappingMonitor/check_traps.py >> /path/to/WoppTrappingMonitor/check_traps.log 2>&1
```

Paths for the CSV and state file are resolved relative to the script, so the working directory doesn't matter.
