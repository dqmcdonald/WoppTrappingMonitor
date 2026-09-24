"""Shared helpers for reading trap data from Trap.NZ's WFS feed.

The API key in trapnz_secrets.py is a Trap.NZ WFS key, so all data comes from
https://io.trap.nz/geo/trapnz-projects/wfs/<KEY>/default rather than the
api2.trap.nz REST API (which needs OAuth2 username/password).
"""

import csv
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone

import requests

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import trapnz_secrets  # noqa: E402

WFS_URL = "https://io.trap.nz/geo/trapnz-projects/wfs/{key}/default"
DEFAULT_CSV = os.path.join(HERE, "TrapLineAssignments.csv")


class TrapNZError(Exception):
    pass


class UnmappedTrapsError(TrapNZError):
    def __init__(self, traps):
        self.traps = traps
        lines = [f"  nid {t['trap_id']}  code {t['code']!r}  project {t['project']!r}" for t in traps]
        super().__init__(
            f"{len(traps)} active trap(s) not found in TrapLineAssignments.csv (by nid or code):\n"
            + "\n".join(lines)
        )


@dataclass
class Trap:
    nid: int
    code: str
    project: str          # key in trapnz_secrets.PROJECT_IDS
    project_id: int
    line: str             # colour from TrapLineAssignments.csv
    last_checked: datetime | None   # None if the trap has never been set

    def days_overdue(self, now=None):
        """Days since last check, or None if never checked."""
        return days_since(self.last_checked, now)


def parse_dt(value):
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def days_since(dt, now=None):
    if dt is None:
        return None
    now = now or datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 86400


def wfs_get(type_name, cql_filter=None, properties=None):
    params = {
        "service": "WFS",
        "version": "2.0.0",
        "request": "GetFeature",
        "typeNames": f"trapnz-projects:{type_name}",
        "outputFormat": "application/json",
    }
    if cql_filter:
        params["cql_filter"] = cql_filter
    if properties:
        params["propertyName"] = ",".join(properties)
    url = WFS_URL.format(key=trapnz_secrets.TRAP_NZ_API_KEY)
    try:
        r = requests.get(url, params=params, timeout=60)
        r.raise_for_status()
    except requests.RequestException as e:
        # Don't leak the API key embedded in the URL.
        raise TrapNZError(f"Trap.NZ request for {type_name} failed: "
                          f"{str(e).replace(trapnz_secrets.TRAP_NZ_API_KEY, '<KEY>')}") from None
    return [f["properties"] for f in r.json()["features"]]


def load_assignments(path=DEFAULT_CSV):
    by_nid, by_code = {}, {}
    with open(path, newline="") as f:
        for row in csv.DictReader(f):
            by_nid[int(row["trap nid"])] = row
            by_code[row["code"].strip()] = row
    return by_nid, by_code


def match_projects(pattern):
    """Return {name: project_id} for configured projects whose name contains pattern."""
    pattern = pattern.lower()
    matches = {name: pid for name, pid in trapnz_secrets.PROJECT_IDS.items()
               if pattern in name.lower()}
    if not matches:
        names = ", ".join(trapnz_secrets.PROJECT_IDS)
        raise TrapNZError(f"No project matches {pattern!r}. Known projects: {names}")
    return matches


def get_traps(projects, csv_path=DEFAULT_CSV):
    """Active traps for {name: project_id}, with line colours from the CSV.

    Raises UnmappedTrapsError if any active trap can't be found in the CSV.
    """
    by_nid, by_code = load_assignments(csv_path)
    name_by_id = {pid: name for name, pid in projects.items()}
    ids = ",".join(str(pid) for pid in projects.values())
    rows = wfs_get(
        "my-projects-traps",
        cql_filter=f"project_id IN ({ids}) AND retired = 0",
        properties=["project", "project_id", "trap_id", "code", "last_record_date", "retired"],
    )
    traps, unmapped = [], []
    for row in rows:
        if row["retired"]:
            continue
        assignment = by_nid.get(int(row["trap_id"])) or by_code.get((row["code"] or "").strip())
        if assignment is None:
            unmapped.append(row)
            continue
        traps.append(Trap(
            nid=int(row["trap_id"]),
            code=row["code"],
            project=name_by_id[int(row["project_id"])],
            project_id=int(row["project_id"]),
            line=assignment["line"],
            last_checked=parse_dt(row["last_record_date"]),
        ))
    if unmapped:
        raise UnmappedTrapsError(unmapped)
    return traps


def fmt_date(dt):
    return dt.astimezone().strftime("%Y-%m-%d") if dt else "never"
