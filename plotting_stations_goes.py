# %%
import os

if os.name == "posix":
    os.system("clear")
else:
    os.system("cls")


import json
import re
import shutil
import socket
import warnings
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import matplotlib as mpl
import matplotlib.pyplot as plt
import astral.sun as astral_sun
from astral import LocationInfo, Depression
import reverse_geocoder as rg
from sunpy.net import Fido, attrs as a
from sunpy.timeseries import TimeSeries
from tqdm import tqdm

socket.setdefaulttimeout(600)
warnings.filterwarnings("ignore")

# csv files are read from the folder this script sits in, plots go to ./output
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.getcwd()

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# every plot goes in a folder named after its date:
#   output/2026-08-18/plot_for_[NSY]_2026-08-18.pdf
def date_folder(date_str):
    path = os.path.join(OUTPUT_DIR, date_str)
    os.makedirs(path, exist_ok=True)
    return path


# GOES flux is often published late, so a day drawn without it is not final.
# Those dates are remembered here, and on the first run more than this many
# hours later the whole date folder is deleted and drawn again. That repeats
# day after day until the flux turns up, and once it does the date is dropped
# from the list and the plot is left alone for good.
RETRY_AFTER_HOURS = 24
PENDING_FILE = os.path.join(OUTPUT_DIR, ".goes_retry.json")

# csv files that are not single station day files are passed over in silence.
# Set this to True while debugging to see which ones were skipped and why.
SHOW_SKIPPED = False

SATELLITES = [19, 18, 17, 16, 15, 14, 13, 12, 11, 10, 8]
FLARE_LEVELS = {"A": 1e-8, "B": 1e-7, "C": 1e-6, "M": 1e-5, "X": 1e-4}


def load_pending():
    # {"2026-08-18": "2026-08-19T03:12:18+00:00"} , date -> last attempt
    try:
        with open(PENDING_FILE) as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_pending(pending):
    try:
        with open(PENDING_FILE, "w") as handle:
            json.dump(pending, handle, indent=2, sort_keys=True)
    except OSError:
        pass


def retry_is_due(date_str, pending):
    # True when this date was drawn without GOES and the wait is over
    stamp = pending.get(date_str)
    if not stamp:
        return False
    try:
        last = datetime.fromisoformat(stamp)
    except ValueError:
        return True
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - last >= timedelta(hours=RETRY_AFTER_HOURS)


# %%
mpl.rcParams.update(
    {
        "font.size": 9,
        "font.family": "serif",
        "axes.linewidth": 0.8,
        "xtick.direction": "in",
        "ytick.direction": "in",
        "xtick.top": True,
        "ytick.right": True,
        "xtick.minor.visible": True,
        "ytick.minor.visible": True,
        "axes.grid": False,
        "text.color": "black",
        "axes.labelcolor": "black",
        "xtick.color": "black",
        "ytick.color": "black",
        "legend.labelcolor": "black",
        "mathtext.fontset": "stix",
    }
)


# %%
def to_hours(t):
    return round(t.hour + t.minute / 60 + t.second / 3600, 5)


def hhmmss(hours):
    minute = (hours % 1) * 60
    sec = (minute % 1) * 60
    return f"{int(hours):02d}:{int(minute):02d}:{int(sec):02d}"


def classify(flux):
    for cls, lvl in reversed(list(FLARE_LEVELS.items())):
        if flux >= lvl:
            return f"{cls}{flux / lvl:.1f}"
    return "sub-A"


def sun_info(lat, lon, day):
    # One geocode plus one sun() call gives city, dawn, sunrise, noon, sunset
    # and dusk. Above roughly 48.5 degrees of latitude, astronomical twilight
    # never arrives around midsummer, and above the polar circles the sun may
    # not rise or set at all. astral raises ValueError in those cases instead
    # of returning a value, which used to kill the whole plot, so each event is
    # asked for on its own and whatever cannot happen is left as None.
    lat, lon = float(lat), float(lon)
    if lat == 21.54 and lon == -39.2:
        lon = abs(lon)  # this station has the wrong sign in its csv header

    place = rg.search((lat, lon), mode=1)[0]
    city = place.get("name", "Unknown City")
    country = place.get("cc", "Unknown Country")
    observer = LocationInfo(city, country, "UTC", lat, lon).observer

    events = {"dawn": None, "sunrise": None, "noon": None, "sunset": None, "dusk": None}
    try:
        whole = astral_sun.sun(
            observer, date=day, dawn_dusk_depression=Depression.ASTRONOMICAL
        )
        for key in events:
            events[key] = to_hours(whole[key])
    except (ValueError, KeyError):
        one_by_one = (
            ("dawn", lambda: astral_sun.dawn(observer, day, Depression.ASTRONOMICAL)),
            ("sunrise", lambda: astral_sun.sunrise(observer, day)),
            ("noon", lambda: astral_sun.noon(observer, day)),
            ("sunset", lambda: astral_sun.sunset(observer, day)),
            ("dusk", lambda: astral_sun.dusk(observer, day, Depression.ASTRONOMICAL)),
        )
        for key, call in one_by_one:
            try:
                events[key] = to_hours(call())
            except (ValueError, KeyError):
                events[key] = None

    # with no sunrise or sunset the whole day is either lit or dark. The sun's
    # elevation at solar noon says which, and the shading follows from that.
    all_day = None
    if events["sunrise"] is None or events["sunset"] is None:
        try:
            midday = astral_sun.noon(observer, day)
            all_day = "day" if astral_sun.elevation(observer, midday) > 0 else "night"
        except (ValueError, KeyError):
            all_day = None

    return {"city": city, "country": country, "all_day": all_day, **events}


# %%
goes_cache = {}


def fetch_goes_xrsb(day):
    # returns (hours, flux, satellite) for the 1-8 A channel, or (None, None, None).
    # tries each satellite until one has data, and remembers the result per day.
    if day in goes_cache:
        return goes_cache[day]

    start, end = f"{day} 00:00", f"{day} 23:59:59"
    goes_cache[day] = (None, None, None)

    for sat in SATELLITES:
        try:
            res = Fido.search(
                a.Time(start, end),
                a.Instrument("XRS"),
                a.goes.SatelliteNumber(sat),
                a.Resolution("avg1m") | a.Resolution("flx1s"),
            )
            if len(res) == 0 or all(len(t) == 0 for t in res):
                continue

            files = Fido.fetch(res, progress=False)
            if not files:
                continue

            df = TimeSeries(files, source="XRS", concatenate=True)
            df = df.to_dataframe().truncate(start, end)
            if "xrsb" not in df.columns:
                continue

            xrsb = df["xrsb"].dropna()
            xrsb = xrsb[xrsb > 0]
            if xrsb.empty:
                continue

            idx = pd.to_datetime(xrsb.index)
            hours = idx.hour + idx.minute / 60 + idx.second / 3600
            goes_cache[day] = (np.asarray(hours), xrsb.to_numpy(), sat)
            return goes_cache[day]
        except Exception:
            continue

    return goes_cache[day]


def fetch_flares(day, sun_data):
    # SWPC flare list from HEK, kept only if the peak happens in daylight.
    # HEK often repeats the same event, so identical rows are dropped.
    res = Fido.search(
        a.Time(f"{day} 00:00:00", f"{day} 23:59:55"),
        a.hek.EventType("FL"),
        a.hek.FRM.Name == "SWPC",
    )
    if not res:
        return []

    table = res["hek"]
    cols = ["event_starttime", "event_peaktime", "event_endtime", "fl_goescls"]
    cols = [c for c in cols if c in table.colnames]
    if len(cols) < 4:
        return []

    rise, sset = sun_data["sunrise"], sun_data["sunset"]
    flares, seen = [], set()

    for row in table[cols].to_pandas().itertuples(index=False):
        try:
            start = to_hours(pd.to_datetime(str(row[0])))
            peak = to_hours(pd.to_datetime(str(row[1])))
            end = to_hours(pd.to_datetime(str(row[2])))
            fclass = str(row[3]).strip() or "?"
        except Exception:
            continue

        key = (start, peak, end, fclass.upper())
        if key in seen:
            continue
        seen.add(key)

        if rise is None or sset is None:
            # polar day keeps every flare, polar night keeps none, because
            # without sunlight there is no ionospheric response to see
            daytime = sun_data.get("all_day") != "night"
        elif sset > rise:
            daytime = rise <= peak <= sset
        else:
            daytime = peak >= rise or peak <= sset

        if daytime:
            flares.append({"start": start, "peak": peak, "end": end, "class": fclass})

    return flares


# %%
def decorate_axis(ax, flares, sun_data, show_labels=False, show_legend=False):
    # same markers on both panels so the vertical lines stay aligned
    for f in flares:
        ax.axvspan(f["start"], f["end"], color="black", alpha=0.10, zorder=0)
        ax.axvline(f["start"], color="black", ls="--", alpha=0.5, lw=1, zorder=0)
        ax.axvline(f["end"], color="black", ls="--", alpha=0.5, lw=1, zorder=0)
        ax.axvline(f["peak"], color="black", ls="-", alpha=0.7, lw=1, zorder=0)
        if show_labels:
            ax.text(
                f["peak"],
                1.07,
                f["class"],
                transform=ax.get_xaxis_transform(),
                color="black",
                ha="center",
                va="top",
                fontweight="bold",
                fontsize=9,
                zorder=3,
                clip_on=False,
            )

    ax.set_xlim([0, 24])
    ax.set_xticks(range(0, 25, 6))

    dawn_h = sun_data["dawn"]
    rise_h = sun_data["sunrise"]
    sset_h = sun_data["sunset"]
    dusk_h = sun_data["dusk"]
    noon_h = sun_data["noon"]

    # night shading. Astronomical night only exists when both dawn and dusk do,
    # which is not the case in a northern summer, so it is simply left off then.
    if dawn_h is not None and dusk_h is not None:
        if rise_h is not None and sset_h is not None and sset_h < rise_h:
            ax.axvspan(dawn_h, 25, color="black", alpha=0.1)
            ax.axvspan(0, dusk_h, color="black", alpha=0.1)
        else:
            ax.axvspan(0, dawn_h, color="black", alpha=0.1)
            ax.axvspan(dusk_h, 25, color="black", alpha=0.1)
    elif sun_data.get("all_day") == "night":
        ax.axvspan(0, 25, color="black", alpha=0.1)

    if dawn_h is not None and rise_h is not None:
        ax.axvspan(dawn_h, rise_h, color="orange", alpha=0.2)
    if sset_h is not None and dusk_h is not None:
        ax.axvspan(sset_h, dusk_h, color="navy", alpha=0.2)

    def label(name, hours):
        return r"$\mathbf{" + f"{name:<9}" + r"\ at:\ " + f"{hhmmss(hours):>8}" + r"}$"

    marks = (
        ("Sunrise", rise_h, "--", "orange", 1.5),
        ("ADawn", dawn_h, "-", "orange", 1),
        ("Sunset", sset_h, "--", "navy", 1.5),
        ("ADusk", dusk_h, "-", "navy", 1),
        ("Noon", noon_h, "-", "red", 2),
    )
    for name, hours, style, colour, width in marks:
        if hours is None:
            continue
        ax.axvline(hours, ls=style, color=colour, lw=width, label=label(name, hours))

    if show_legend:
        # say why a line is absent instead of leaving the reader guessing
        missing = [name for name, hours, _, _, _ in marks if hours is None]
        if missing:
            if sun_data.get("all_day") == "day":
                why = "the sun does not set here on this date"
            elif sun_data.get("all_day") == "night":
                why = "the sun does not rise here on this date"
            else:
                why = "this latitude gets no astronomical darkness on this date"
            ax.figure.text(
                0.01,
                0.01,
                "no %s marked: %s" % (", ".join(missing).lower(), why),
                fontsize=8,
                color="grey",
            )

    if show_legend:
        handles, labels = ax.get_legend_handles_labels()
        if handles:
            ax.legend(
                handles,
                labels,
                prop={"family": "monospace", "weight": "bold", "size": 8},
                loc="upper right",
                frameon=False,
                ncol=1,
            )


# %%
def read_vlf_file(filename, pending, cleared):
    # header lines start with '#' and hold "key = value" pairs
    metadata = {}
    header_lines = 0
    with open(filename, "r") as f:
        for line in f:
            if not line.startswith("#"):
                break
            header_lines += 1
            if "=" in line:
                key, value = line.split("=", 1)
                metadata[key.replace("#", "").strip()] = value.strip()

    messages = []
    start_time = pd.to_datetime(metadata["UTC_StartTime"])
    date_str = start_time.strftime("%Y-%m-%d")
    file_name = f"plot_for_[{metadata['StationID']}]_{date_str}.pdf"
    out_dir = os.path.join(OUTPUT_DIR, date_str)
    exported_file = os.path.join(out_dir, file_name)

    if os.path.exists(exported_file):
        if not retry_is_due(date_str, pending):
            return [f"   Skipping : {file_name} already exists."]
        # the wait is over and there was still no flux last time, so the whole
        # date folder goes and every station of that day is drawn again. Once
        # per run, otherwise the second station would wipe the first one.
        if date_str not in cleared:
            shutil.rmtree(out_dir, ignore_errors=True)
            cleared.add(date_str)
            messages.append(
                f"   {date_str}: no GOES flux last time and "
                f"{RETRY_AFTER_HOURS} h have passed, folder deleted, drawing again"
            )

    messages.append(f"   Generating: {file_name}...")

    data = pd.read_csv(filename, skiprows=header_lines, names=["Timestamp", "Signal"])
    data["Timestamp"] = pd.to_datetime(data["Timestamp"])
    # the seconds have to be in here. Without them every sample inside a minute
    # lands on the same x, so at a 5 second log interval twelve readings stack
    # on one point and the line jumps straight up and down at each minute mark.
    # That shows up as a stutter along the whole curve.
    t = data["Timestamp"].dt
    data["Hour"] = t.hour + t.minute / 60 + t.second / 3600

    sun_data = sun_info(metadata["Latitude"], metadata["Longitude"], start_time.date())
    flares = fetch_flares(date_str, sun_data)

    # top panel = GOES x-ray flux, bottom panel = SID signal, shared x-axis
    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(21, 9),
        constrained_layout=True,
        sharex=True,
        gridspec_kw={"height_ratios": [1, 1.4]},
    )

    ax1.set_yscale("log")
    ax1.set_ylim(1e-9, 1e-3)
    ax1.set_ylabel(r"$\mathbfit{Flux\ (W\,m^{-2})}$")

    g_hours, g_flux, g_sat = fetch_goes_xrsb(date_str)
    if g_hours is not None:
        ax1.plot(g_hours, g_flux, color="crimson", linewidth=1.0)
        ax1.set_title(
            rf"GOES-{g_sat} X-ray Flux (1$-$8 $\AA$)", fontsize=10, loc="left"
        )
        for cls, lvl in FLARE_LEVELS.items():
            ax1.axhline(lvl, color="grey", ls=":", lw=0.6, alpha=0.7, zorder=0)
            ax1.text(
                1.005,
                lvl,
                cls,
                transform=ax1.get_yaxis_transform(),
                va="center",
                fontsize=8,
                color="grey",
                clip_on=False,
            )
        messages.append(
            f"   GOES-{g_sat} used | daily peak: {classify(np.nanmax(g_flux))}"
        )
    else:
        ax1.set_title(r"GOES X-ray Flux (1$-$8 $\AA$)", fontsize=10, loc="left")
        ax1.text(
            0.5,
            0.5,
            "no GOES satellite returned 1-8 $\\AA$ data for this date",
            transform=ax1.transAxes,
            ha="center",
            va="center",
            color="grey",
        )
        ax1.text(
            0.5,
            0.36,
            f"the flux is often published late, so this plot is not final: it is "
            f"deleted and drawn again on the\nfirst run more than {RETRY_AFTER_HOURS} "
            f"hours from now, and every day after that until the flux appears",
            transform=ax1.transAxes,
            ha="center",
            va="center",
            color="grey",
            fontsize=8,
        )
        messages.append("   No GOES 1-8 A data available for this date.")
        messages.append(
            f"   It will be deleted and redrawn after {RETRY_AFTER_HOURS} h, "
            f"and every day until the flux is published."
        )

    # drawn exactly as it sits in the file, no smoothing added here. Whether it
    # arrives smoothed already is the monitor's business, and the header says so.
    ax2.plot(
        data["Hour"],
        data["Signal"],
        color="black",
        linewidth=0.9,
    )
    ax2.set_ylabel(r"$\mathbfit{Signal\ Strength}$")
    ax2.set_xlabel(r"$\mathbfit{UTC\ Time\ (Hours)}$")
    if str(metadata.get("LogType", "")).strip().lower() == "filtered":
        lower_title = "signal as recorded (BEMA already applied by supersid)"
    else:
        lower_title = "signal as recorded (raw, no filter applied)"
    ax2.set_title(lower_title, fontsize=10, loc="left")
    ax2.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

    # flare classes only on top, legend only on bottom
    decorate_axis(ax1, flares, sun_data, show_labels=True)
    decorate_axis(ax2, flares, sun_data, show_legend=True)

    plt.suptitle(
        f"{metadata['Site']} | {sun_data['city']} | {sun_data['country']} "
        f"{metadata['StationID']} | {metadata['Frequency']}Hz | {date_str}"
    )
    os.makedirs(out_dir, exist_ok=True)
    fig.savefig(exported_file)
    plt.close(fig)

    # remember the date while the flux is still missing, forget it once it is
    # there, so a finished plot is never touched again
    if g_hours is None:
        pending[date_str] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    else:
        pending.pop(date_str, None)
    save_pending(pending)

    return messages


# %%
def sort_key(filepath):
    match = re.search(r"(\d{4}-\d{2}-\d{2})|(\d{8})", filepath)
    return match.group() if match else filepath


def is_station_day_file(path):
    """True only for a one-station day file, the kind this script can plot.

    Everything else in the data folder is ignored without a word: vlf_table.csv
    has no '#' header at all, and hourly_current_buffers... is the combined
    dump, which carries 'Stations' and 'Frequencies' rather than the
    'StationID' and 'Frequency' used here. Both used to reach the plotting code
    and fail with a bare KeyError.
    """
    try:
        with open(path, "r") as handle:
            header = []
            for line in handle:
                if not line.startswith("#"):
                    break
                header.append(line)
                if len(header) > 60:
                    break
    except OSError:
        return False
    text = "".join(header)
    return "UTC_StartTime" in text and "StationID" in text


csv_files = []
skipped = []
for name in sorted(os.listdir(SCRIPT_DIR)):
    if not name.endswith(".csv"):
        continue
    full = os.path.join(SCRIPT_DIR, name)
    try:
        if os.stat(full).st_size == 0:
            skipped.append(f"{name} (empty)")
            continue
    except OSError:
        continue
    if not is_station_day_file(full):
        skipped.append(f"{name} (not a single station day file)")
        continue
    csv_files.append(full)

csv_files.sort(key=sort_key)

if SHOW_SKIPPED and skipped:
    for name in skipped:
        print(f"   ignored {name}")

# reverse_geocoder prints "Loading formatted geocoded file..." on its first call,
# so trigger it here instead of in the middle of the progress bar
rg.search((0.0, 0.0), mode=1)

pending = load_pending()
cleared = set()

for filepath in tqdm(csv_files, unit="file"):
    try:
        messages = read_vlf_file(filepath, pending, cleared)
    except Exception as exc:
        messages = [f"   Failed on {os.path.basename(filepath)}: {exc}"]
    for msg in messages:
        tqdm.write(msg)
    tqdm.write("")
