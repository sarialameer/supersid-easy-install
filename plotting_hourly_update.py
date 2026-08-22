# %%
import os
import sys

if sys.stdout.isatty():
    os.system("clear" if os.name == "posix" else "cls")


import re
import shutil
import time
import warnings

import pandas as pd
import matplotlib as mpl

mpl.use("Agg")  # no screen needed, the pdf is written straight to disk

import matplotlib.pyplot as plt
import astral.sun as astral_sun
from astral import LocationInfo, Depression
import reverse_geocoder as rg

warnings.filterwarnings("ignore")

try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.getcwd()

OUTPUT_DIR = os.path.join(SCRIPT_DIR, "hourly_output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# where the csv files are. leave it as SCRIPT_DIR if they sit next to this
# script, otherwise put supersid's data_path here, for example
# DATA_DIR = "/home/pi/supersid/Data"
DATA_DIR = SCRIPT_DIR

# supersid's bema filter: lowest value in a window around each point, then a
# moving average over those minima. wing 6 means a 13 point window, which is
# about a minute at a 5 second log interval. set to 0 to draw the raw values
BEMA_WING = 6

# the lower panel is a plain moving average over this many minutes. At the usual
# five second log interval ten minutes is 120 samples.
MOVING_AVG_MINUTES = 10

# The hourly buffer holds every slot of the day in advance and each one reads 0
# until the monitor reaches it, so early in the day most of the file is zeros.
# They are drawn as they are, because a reading of 0 can also mean the
# transmitter was off air, and dropping every zero hides that. Set this to False
# to leave them out and let the y scale follow the recorded part only.
PLOT_ZEROS = True


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
    # work in whole seconds, int() alone drops a second on values like 12.86528
    total = int(round(hours * 3600))
    return f"{total // 3600:02d}:{total % 3600 // 60:02d}:{total % 60:02d}"


def sun_info(lat, lon, day):
    # One geocode plus one sun() call gives city, dawn, sunrise, noon, sunset
    # and dusk. Above roughly 48.5 degrees of latitude, astronomical twilight
    # never arrives around midsummer, and above the polar circles the sun may
    # not rise or set at all. astral raises ValueError in those cases instead
    # of returning a value, so each event is asked for on its own and whatever
    # cannot happen is left as None.
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

    all_day = None
    if events["sunrise"] is None or events["sunset"] is None:
        try:
            midday = astral_sun.noon(observer, day)
            all_day = "day" if astral_sun.elevation(observer, midday) > 0 else "night"
        except (ValueError, KeyError):
            all_day = None

    return {"city": city, "country": country, "all_day": all_day, **events}


# %%
def decorate_axis(ax, sun_data, show_legend=True):
    ax.set_xlim([0, 24])
    ax.set_xticks(range(0, 25, 6))

    dawn_h = sun_data["dawn"]
    rise_h = sun_data["sunrise"]
    sset_h = sun_data["sunset"]
    dusk_h = sun_data["dusk"]
    noon_h = sun_data["noon"]

    # astronomical night only exists when both dawn and dusk do, which is not
    # the case in a northern summer, so it is simply left off then
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

    missing = [name for name, hours, _, _, _ in marks if hours is None]
    if missing and show_legend:
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

    handles, labels = ax.get_legend_handles_labels()
    if handles and show_legend:
        ax.legend(
            handles,
            labels,
            prop={"family": "monospace", "weight": "bold", "size": 8},
            loc="upper right",
            frameon=False,
            ncol=1,
        )


# %%
def read_header(filename):
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
    return metadata, header_lines


def split_list(value):
    return [v.strip() for v in str(value).split(",") if v.strip()]


def station_names(metadata):
    return split_list(metadata.get("Stations", metadata.get("StationID", "Signal")))


def read_data(filename, metadata, header_lines):
    # the file is a whole-day buffer written in advance: every slot of the day
    # already exists and holds 0 until the monitor fills it. Those zeros are
    # kept and drawn, see PLOT_ZEROS at the top of this file.
    stations = station_names(metadata)

    data = pd.read_csv(filename, skiprows=header_lines, header=None)
    columns = ["Timestamp"] + stations
    if len(columns) != data.shape[1]:
        # header and data disagree on the station count, fall back to numbering
        stations = [f"S{i}" for i in range(1, data.shape[1])]
        columns = ["Timestamp"] + stations

    data.columns = columns
    data["Timestamp"] = pd.to_datetime(data["Timestamp"])
    t = data["Timestamp"].dt
    data["Hour"] = t.hour + t.minute / 60 + t.second / 3600

    for st in stations:
        data[st] = pd.to_numeric(data[st], errors="coerce")

    return data, stations


def bema_filter(values, wing):
    # same idea as SidFile.filter_buffer in supersid: take the lowest value in
    # the window around each point so the quiet background is followed, then
    # smooth those minima with one moving average. supersid uses 2*wing points
    # for the min and 2*wing+1 for the average, so the same is done here.
    if wing < 1:
        return values
    low = values.rolling(2 * wing, center=True, min_periods=1).min()
    return low.rolling(2 * wing + 1, center=True, min_periods=1).mean()


# %%
def plot_station(metadata, data, station, freq, sun_data, date_str):
    full = data[["Hour", station]].dropna()
    recorded = full[full[station] != 0]

    if recorded.empty:
        return f"   {station}: nothing recorded yet on {date_str}"

    # everything is drawn, zeros included, unless PLOT_ZEROS says otherwise.
    # The times in the title still come from the non zero part, so it keeps
    # telling you how far the recording has actually got.
    signal = full if PLOT_ZEROS else recorded

    # two panels sharing the x axis, so the sun lines stay lined up:
    # the bema curve on top, a plain moving average underneath
    fig, (ax1, ax2) = plt.subplots(
        2,
        1,
        figsize=(21, 10),
        constrained_layout=True,
        sharex=True,
        gridspec_kw={"height_ratios": [1, 1]},
    )

    # supersid hardcodes log_type='raw' for the hourly dump, whatever log_type
    # says in the config, so these values are normally unfiltered and the bema
    # filter is applied here instead. If a file ever does arrive already
    # filtered, its header says so and nothing further is applied.
    already_filtered = str(metadata.get("LogType", "raw")).strip().lower() == "filtered"
    wing = 0 if already_filtered else BEMA_WING

    ax1.plot(signal["Hour"], bema_filter(signal[station], wing),
             color="black", linewidth=0.9)
    ax1.set_ylabel(r"$\mathbfit{Signal\ Strength}$")
    if already_filtered:
        title = "filtered by supersid already (LogType = filtered), nothing added here"
    elif wing > 0:
        title = f"BEMA wing {wing} (applied here, the csv itself is raw)"
    else:
        title = "raw, no filter"
    ax1.set_title(title, fontsize=10, loc="left")
    ax1.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

    # the window is worked out from the log interval in the header rather than
    # assumed, so ten minutes stays ten minutes if the interval is not five
    # seconds. At the usual five seconds this is the 120 samples you would
    # expect.
    try:
        log_interval = float(metadata.get("LogInterval", 5))
    except ValueError:
        log_interval = 5.0
    if log_interval <= 0:
        log_interval = 5.0
    window = max(1, int(round(MOVING_AVG_MINUTES * 60 / log_interval)))

    ax2.plot(
        signal["Hour"],
        signal[station].rolling(window=window, min_periods=1).mean(),
        color="black",
        linewidth=0.9,
    )
    ax2.set_ylabel(r"$\mathbfit{Signal\ Strength}$")
    ax2.set_xlabel(r"$\mathbfit{UTC\ Time\ (Hours)}$")
    ax2.set_title(
        f"{MOVING_AVG_MINUTES} minute moving average ({window} samples)",
        fontsize=10,
        loc="left",
    )
    ax2.ticklabel_format(axis="y", style="sci", scilimits=(0, 0))

    # the same markers on both panels, the legend only on the lower one
    decorate_axis(ax1, sun_data, show_legend=False)
    decorate_axis(ax2, sun_data, show_legend=True)

    if wing > 0:
        # supersid filters the full day buffer at once and wraps the end of the
        # day onto the start, so its result is only final once the day is over.
        # here the day is still being recorded, so the curve is provisional and
        # the two edges are the least trustworthy part of it
        ax2.text(
            0.0,
            -0.16,
            "bema is exact only over a complete day, this is recomputed each "
            "hour from the partial buffer",
            transform=ax2.transAxes,
            fontsize=8,
            color="grey",
        )

    first = hhmmss(recorded["Hour"].iloc[0])
    last = hhmmss(recorded["Hour"].iloc[-1])
    plt.suptitle(
        f"{metadata.get('Site', '?')} | {sun_data['city']} | {sun_data['country']} "
        f"{station} | {freq}Hz | {date_str} | recorded {first} to {last} UTC"
    )

    # straight into hourly_output, no date folder. The name carries the date, so
    # each round of the same day overwrites the last one and the file always
    # holds everything recorded so far. Yesterday's file is deleted once the
    # date rolls over, and the daily GOES script keeps the finished version.
    file_name = f"plot_for_[{station}]_{date_str}.pdf"
    fig.savefig(os.path.join(OUTPUT_DIR, file_name))
    plt.close(fig)

    return f"   {file_name} | {len(recorded)} samples | {first} to {last} UTC"


def clear_old_plots(date_str):
    # the day is over once the csv carries a new date, so anything not carrying
    # today's date goes and only today's pdfs stay. The finished version of
    # those days is what the daily GOES script writes into its own output
    # folder, so nothing is lost here.
    removed = 0
    for name in os.listdir(OUTPUT_DIR):
        path = os.path.join(OUTPUT_DIR, name)
        if date_str in name:
            continue
        try:
            if os.path.isdir(path):
                # a date folder from an earlier version of this script
                shutil.rmtree(path, ignore_errors=True)
                removed += 1
            elif name.endswith(".pdf"):
                os.remove(path)
                removed += 1
        except OSError:
            pass
    return removed


def plot_file(filename, wanted):
    metadata, header_lines = read_header(filename)
    start_time = pd.to_datetime(metadata["UTC_StartTime"])
    date_str = start_time.strftime("%Y-%m-%d")

    data, stations = read_data(filename, metadata, header_lines)
    freqs = split_list(metadata.get("Frequencies", metadata.get("Frequency", "?")))

    if wanted != "all":
        stations = [s for s in stations if s == wanted] or stations

    # the same for every station in this file, so it is worked out once
    sun_data = sun_info(metadata["Latitude"], metadata["Longitude"], start_time.date())

    all_stations = station_names(metadata)
    messages = []
    for station in stations:
        i = all_stations.index(station) if station in all_stations else -1
        freq = freqs[i] if 0 <= i < len(freqs) else "?"
        messages.append(plot_station(metadata, data, station, freq, sun_data, date_str))

    removed = clear_old_plots(date_str)
    if removed:
        messages.append(f"   day changed, {removed} old plot(s) deleted")
    return messages


# %%
DATE_PATTERN = re.compile(r"(\d{4}-\d{2}-\d{2})|(\d{8})")

# supersid also drops its end of day files in the same folder, one per station
# with sid_format, and those carry a date too. only the hourly dump is wanted,
# so the name has to start with this
FILE_PREFIX = "hourly_current_buffers"


def file_date(name):
    # the date sits at the end of the name, whatever separators are used:
    # hourly_current_buffers.raw.ext.2026-08-17.csv, ..._raw_ext_2026-08-17.csv
    match = DATE_PATTERN.search(name)
    if not match:
        return None
    text = match.group()
    return text if "-" in text else f"{text[:4]}-{text[4:6]}-{text[6:]}"


def find_data_file():
    # today's file wins. if it is not written yet, take the newest one on disk,
    # so the date rollover needs no restart
    found = {}
    skipped = []
    for name in sorted(os.listdir(DATA_DIR)):
        if not name.endswith(".csv"):
            continue
        if not name.startswith(FILE_PREFIX):
            skipped.append(f"{name} (not an hourly file)")
            continue
        day = file_date(name)
        if day is None:
            skipped.append(f"{name} (no date in the name)")
            continue
        full = os.path.join(DATA_DIR, name)
        try:
            if os.stat(full).st_size == 0:
                skipped.append(f"{name} (empty)")
                continue
            # if a day somehow has more than one file, keep the newest
            if day in found and os.path.getmtime(full) < os.path.getmtime(found[day]):
                continue
        except OSError:
            continue  # the file was deleted while the folder was being read
        found[day] = full

    if not found:
        print(f"   looked in {DATA_DIR}")
        for name in skipped:
            print(f"   ignored {name}")
        return None

    today = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    return found.get(today, found[max(found)])


def choose_station(filename):
    metadata, _ = read_header(filename)
    stations = station_names(metadata)
    if len(stations) == 1:
        return stations[0]

    print("\nstations in this file:")
    for i, st in enumerate(stations, 1):
        print(f"  {i}. {st}")
    print("  0. all of them")

    try:
        answer = input("which one? ").strip()
    except EOFError:
        return "all"  # not running in a terminal

    if answer == "0" or answer.lower() == "all":
        return "all"
    if answer.isdigit() and 1 <= int(answer) <= len(stations):
        return stations[int(answer) - 1]
    if answer in stations:
        return answer

    print("not a valid choice, plotting all of them")
    return "all"


# %%
wanted = None

try:
    while True:
        print(f"[{pd.Timestamp.now('UTC'):%Y-%m-%d %H:%M} UTC]")

        filename = find_data_file()
        if filename is None:
            # the monitor writes its first file only after a full hour
            print("   no csv found, waiting")
        else:
            if wanted is None:
                wanted = choose_station(filename)
            try:
                for msg in plot_file(filename, wanted):
                    print(msg)
            except Exception as exc:
                print(f"   failed on {os.path.basename(filename)}: {exc}")

        # a couple of minutes past the hour, so supersid has finished writing
        # its hourly dump before this reads it
        wait = 3600 - (time.time() % 3600) + 120
        print(f"   next update in {int(wait // 60)} min\n")
        time.sleep(wait)
except KeyboardInterrupt:
    print("stopped")
