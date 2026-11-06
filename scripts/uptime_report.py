#!/usr/bin/env python3
"""uptime_report.py — measure gate 1.1's uptime from Actions run history.

The acceptance line is "engine + HSM + economy uptime >= 99% measured over 7
consecutive days". This script measures it from the `uptime` workflow's runs:
every run is a beat; success rate over the window is the uptime. Nothing is
declared — the number comes off the API.

Usage:
  GITHUB_TOKEN=… python3 scripts/uptime_report.py            # last 7 days
  GITHUB_TOKEN=… python3 scripts/uptime_report.py --days 14  # custom window

Stdlib only (ADR-0007).
"""
import argparse
import json
import os
import time
import urllib.request
from datetime import datetime, timedelta, timezone

REPO = "roshpinacare-sys/dynamis"
WORKFLOW = "uptime.yml"


def fetch_runs(days: int) -> list[dict]:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise SystemExit("GITHUB_TOKEN required (read-only Actions access)")
    since = (datetime.now(timezone.utc) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
    url = (f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}"
           f"/runs?per_page=200&created=>={since}")
    runs: list[dict] = []
    page = 1
    while True:
        req = urllib.request.Request(f"{url}&page={page}",
                                     headers={"Authorization": f"Bearer {token}",
                                              "Accept": "application/vnd.github+json"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            batch = json.load(resp).get("workflow_runs", [])
        if not batch:
            break
        runs.extend(batch)
        if len(batch) < 200:
            break
        page += 1
    return runs


def main() -> int:
    ap = argparse.ArgumentParser(description="gate 1.1 uptime, measured")
    ap.add_argument("--days", type=int, default=7)
    ns = ap.parse_args()
    runs = fetch_runs(ns.days)
    done = [r for r in runs if r["status"] == "completed"]
    ok = [r for r in done if r["conclusion"] == "success"]
    beats = len(runs)
    if beats == 0:
        print(json.dumps({"uptime_bps": None, "beats": 0,
                          "note": f"no {WORKFLOW} runs in the last {ns.days} days — "
                                  "the harness exists; the window is calendar time"}))
        return 0
    # Basis points, integer — 9900 bps = 99.00%. ADR-0007: the wire is
    # integers-only, and this number travels inside the hash-stamped daily
    # record, so it must recompute under the canonical hash. 10000 = 100.00%.
    uptime_bps = round(10000 * len(ok) / len(done))
    gate_pass = uptime_bps >= 9900
    print(json.dumps({
        "window_days": ns.days, "beats": beats,
        "completed": len(done), "succeeded": len(ok),
        "uptime_bps": uptime_bps, "gate_1_1_pass": bool(gate_pass and ns.days >= 7),
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
