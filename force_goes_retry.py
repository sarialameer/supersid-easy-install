#!/usr/bin/env python3
"""Force the daily GOES plots to be redrawn without waiting for the 24 hour wait.

plotting_stations_goes.py keeps a small file, output/.goes_retry.json, listing
every date it drew without GOES x-ray flux and the time it last tried. It only
redraws a date once RETRY_AFTER_HOURS have passed since that time. This script
backdates those timestamps so the next run treats them as due.

Put this next to plotting_stations_goes.py, in the data folder.

    python3 force_goes_retry.py                 show what is waiting
    python3 force_goes_retry.py --all           mark every date as due
    python3 force_goes_retry.py 2026-08-21      mark one date as due
    python3 force_goes_retry.py --clear 2026-08-21
                                                forget a date, so its plot is
                                                kept as final and never redrawn

Then run the plots:

    ./tools/plot_daily_goes.sh --now
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.getcwd()

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
PENDING_FILE = os.path.join(OUTPUT_DIR, ".goes_retry.json")

# far enough back that any sane RETRY_AFTER_HOURS has already elapsed
BACKDATE_HOURS = 24 * 400


def load():
    try:
        with open(PENDING_FILE) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        print(f"could not read {PENDING_FILE}: {exc}")
        sys.exit(1)


def save(pending):
    try:
        os.makedirs(OUTPUT_DIR, exist_ok=True)
        with open(PENDING_FILE, "w") as handle:
            json.dump(pending, handle, indent=2, sort_keys=True)
    except OSError as exc:
        print(f"could not write {PENDING_FILE}: {exc}")
        sys.exit(1)


def show(pending):
    if not pending:
        print("nothing is waiting for GOES data.")
        print("every plot in output/ has its flux and none will be redrawn.")
        return
    now = datetime.now(timezone.utc)
    print(f"{len(pending)} date(s) waiting for GOES flux:")
    print()
    for date_str in sorted(pending):
        stamp = pending[date_str]
        try:
            last = datetime.fromisoformat(stamp)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            hours = (now - last).total_seconds() / 3600
            print(f"   {date_str}   last tried {hours:.1f} h ago")
        except ValueError:
            print(f"   {date_str}   last tried {stamp}")
    print()
    print("run this with --all to have them all redrawn on the next run.")


def main():
    args = [a for a in sys.argv[1:]]
    pending = load()

    if not args:
        show(pending)
        return

    if args[0] == "--clear":
        wanted = args[1:]
        if not wanted:
            print("give at least one date, for example: --clear 2026-08-21")
            sys.exit(1)
        gone = [d for d in wanted if pending.pop(d, None) is not None]
        save(pending)
        if gone:
            print("no longer waiting for flux, kept as final: " + ", ".join(gone))
        else:
            print("none of those dates were in the list.")
        return

    stamp = (datetime.now(timezone.utc) - timedelta(hours=BACKDATE_HOURS))
    stamp = stamp.isoformat(timespec="seconds")

    if args[0] == "--all":
        if not pending:
            print("nothing is waiting, so there is nothing to force.")
            return
        for date_str in pending:
            pending[date_str] = stamp
        save(pending)
        print(f"{len(pending)} date(s) marked as due: " + ", ".join(sorted(pending)))
    else:
        missing = [d for d in args if d not in pending]
        for date_str in args:
            pending[date_str] = stamp
        save(pending)
        print("marked as due: " + ", ".join(args))
        if missing:
            print(
                "note, these were not in the list and have been added: "
                + ", ".join(missing)
            )
            print("that only matters if a plot for them already exists.")

    print()
    print("now run the plots:")
    print("   ./tools/plot_daily_goes.sh --now")
    print("or, from this folder:")
    print("   python3 plotting_stations_goes.py")


if __name__ == "__main__":
    main()
