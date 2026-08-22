#!/bin/bash
#
# install_supersid.sh
#
# Installs sberl/supersid on Debian / Ubuntu / Raspberry Pi OS, picks your VLF
# transmitters with vlf_transit.py, writes Config/supersid.cfg, copies the
# plotting scripts into your data folder and sets up cron and a bash alias.
#
# Put these files in the same folder as this script before running it:
#
#   vlf_transit.py               finds the transmitters closest to you
#   plotting_stations_goes.py    daily plots with GOES x-ray flux
#   plotting_hourly_update.py    hourly plot of the running day
#   force_goes_retry.py          redraws a day without waiting for the retry
#
# Run it as your normal user, NOT with sudo. It calls sudo only for apt.
#
#   chmod +x install_supersid.sh
#   ./install_supersid.sh
#
# SUPERSID_INSTALL_NOTES.md explains every command this script runs.

set -e
trap 'echo ""; echo "Something failed on line $LINENO. Scroll up to see the error."; exit 1' ERR

REPO_URL="https://github.com/sberl/supersid.git"
SESSION="supersid"

# the three python files this script installs next to your data
VLF_SCRIPT="vlf_transit.py"
DAILY_SCRIPT="plotting_stations_goes.py"
HOURLY_SCRIPT="plotting_hourly_update.py"
RETRY_SCRIPT="force_goes_retry.py"

# folder this script was started from, that is where the python files must be
SELF_DIR="$(cd "$(dirname "$0")" && pwd)"


# ---------------------------------------------------------------------------
# question helpers
#
# Every prompt ends with " > " so you always know where to type. The bit in
# front of the > tells you what pressing Enter does.
# ---------------------------------------------------------------------------

title() {
    echo ""
    echo "==================================================================="
    echo " $1"
    echo "==================================================================="
}

# ask "question" "default"
# Enter accepts the default that is shown.
ask() {
    local answer=""
    read -r -p "$1 [Enter = $2] > " answer
    echo "${answer:-$2}"
}

# ask_required "question"
# No default. Enter is refused, you have to type something.
ask_required() {
    local answer=""
    while [ -z "$answer" ]; do
        read -r -p "$1 (required, cannot be empty) > " answer
        if [ -z "$answer" ]; then
            echo "  There is no default for this one, please type a value." >&2
        fi
    done
    echo "$answer"
}

# ask_needed "question" "default"
# Has a default, but an empty result is not allowed.
ask_needed() {
    local answer=""
    while [ -z "$answer" ]; do
        answer=$(ask "$1" "$2")
        if [ -z "$answer" ]; then
            echo "  This value is mandatory, please type one." >&2
        fi
    done
    echo "$answer"
}

# ask_optional "question"
# Enter skips the whole thing and leaves it empty on purpose.
ask_optional() {
    local answer=""
    read -r -p "$1 (Enter = skip this) > " answer
    echo "$answer"
}

# yes_no "question" "y"
# Type y or n. Enter takes the letter that is shown.
yes_no() {
    local answer=""
    read -r -p "$1 (y/n) [Enter = $2] > " answer
    answer="${answer:-$2}"
    case "$answer" in
        [Yy]*) return 0 ;;
        *)     return 1 ;;
    esac
}

# is_number "42"
is_number() {
    echo "$1" | grep -qE '^[0-9]+$'
}


# ---------------------------------------------------------------------------
# 0. checks before we touch anything
# ---------------------------------------------------------------------------

if [ ! -t 0 ]; then
    echo "This script asks questions, so run it from a terminal."
    exit 1
fi

if [ "$(id -u)" -eq 0 ]; then
    echo "Do not run this with sudo. Everything would end up owned by root and"
    echo "the virtual environment would live in /root. Run it as yourself."
    exit 1
fi

if ! command -v apt >/dev/null 2>&1; then
    echo "No apt found. This script is written for Debian, Ubuntu, Mint and"
    echo "Raspberry Pi OS. On other distributions install the same packages by"
    echo "hand and then follow the notes file."
    exit 1
fi

clear
cat <<'INTRO'
===================================================================
 SuperSID installer
===================================================================

How the questions work. Every prompt ends with a > and the part in
front of it tells you what to do:

  [Enter = something]           press Enter to accept that value,
                                or type your own to replace it
  (required, cannot be empty)   there is no default, you must type
  (y/n) [Enter = y]             type y or n, Enter takes the letter shown
  (Enter = skip this)           press Enter to skip the step entirely
  (type a number) [Enter = 1]   pick a line from the list above it

Nothing is written to your disk until the questions are done, and
you can stop at any point with Ctrl+C.

INTRO
read -r -p "Press Enter to start > " _


# ---------------------------------------------------------------------------
# 1. where do you want it
# ---------------------------------------------------------------------------

title "1. Install location"

echo "SuperSID will be cloned into a folder called supersid inside the path"
echo "you give below. The default is fine for most people."
echo ""

INSTALL_BASE=$(ask "Parent folder" "$HOME/projects")
INSTALL_BASE="${INSTALL_BASE/#\~/$HOME}"

APP_DIR="$INSTALL_BASE/supersid"
VENV_DIR="$APP_DIR/supersid"
CFG_FILE="$APP_DIR/Config/supersid.cfg"
TOOLS_DIR="$APP_DIR/tools"
LOG_DIR="$APP_DIR/logs"

echo ""
echo "Program      : $APP_DIR"
echo "Environment  : $VENV_DIR"

# check the python files are where we expect before doing any work
MISSING=""
for f in "$VLF_SCRIPT" "$DAILY_SCRIPT" "$HOURLY_SCRIPT"; do
    if [ ! -f "$SELF_DIR/$f" ]; then
        MISSING="$MISSING $f"
    fi
done

if [ -n "$MISSING" ]; then
    echo ""
    echo "These files are not next to install_supersid.sh:$MISSING"
    echo "Looked in: $SELF_DIR"
    echo ""
    echo "If you named the hourly script differently, rename it to"
    echo "$HOURLY_SCRIPT and start again. Without them the install still"
    echo "works, you just enter the stations by hand and get no plots."
    echo ""
    if ! yes_no "Carry on without them?" "n"; then
        exit 1
    fi
fi

mkdir -p "$INSTALL_BASE"


# ---------------------------------------------------------------------------
# 2. system packages
# ---------------------------------------------------------------------------

title "2. System packages"

echo "Installing git, the ALSA headers, tk, tmux and the build tools."
echo "sudo will ask for your password."
echo ""

sudo apt update
sudo apt install -y \
    git curl cron tmux \
    alsa-utils libasound2-dev \
    build-essential python3-dev python3-venv python3-tk


# ---------------------------------------------------------------------------
# 3. get the code
# ---------------------------------------------------------------------------

title "3. Downloading SuperSID"

if [ -d "$APP_DIR/.git" ]; then
    echo "Already cloned, pulling the latest version instead."
    git -C "$APP_DIR" pull --ff-only || echo "Pull failed, keeping what is on disk."
else
    git clone "$REPO_URL" "$APP_DIR"
fi

cd "$APP_DIR"
mkdir -p "$TOOLS_DIR" "$LOG_DIR"

SHIPPED_CFG="$APP_DIR/Config/supersid.cfg.shipped"
if [ ! -f "$SHIPPED_CFG" ] && [ -f "$CFG_FILE" ]; then
    cp "$CFG_FILE" "$SHIPPED_CFG"
fi


# ---------------------------------------------------------------------------
# 4. virtual environment
# ---------------------------------------------------------------------------

title "4. Virtual environment"

if [ ! -f "$VENV_DIR/bin/activate" ]; then
    python3 -m venv supersid
fi

source "$VENV_DIR/bin/activate"

echo "Using $(python3 --version) from $VENV_DIR"
echo ""

pip install --upgrade pip
pip install setuptools wheel

# Python 3.12 and newer cannot build the old pinned numpy and pandas, so drop
# the pins and let pip fetch the current wheels. Harmless if already done.
sed -i 's/numpy~=1.23.0/numpy/g' requirements.txt
sed -i 's/pandas~=2.1.0/pandas/g' requirements.txt

pip install -r requirements.txt


# ---------------------------------------------------------------------------
# 5. packages for the plotting scripts
# ---------------------------------------------------------------------------

title "5. Packages for the plotting scripts"

echo "The plotting scripts need a few more packages than SuperSID itself:"
echo ""
echo "  reportlab           the pdf table from vlf_transit.py"
echo "  astral              sunrise, sunset and solar noon"
echo "  reverse_geocoder    turns your coordinates into a city name"
echo "  tqdm                the progress bar on the daily plots"
echo "  sunpy               GOES x-ray flux and the flare list, with three"
echo "                      extras: net downloads the data, timeseries reads"
echo "                      the netCDF and CDF files it arrives in, and"
echo "                      visualization is pulled in by timeseries itself"
echo ""
echo "sunpy is the big one, a few hundred MB with its dependencies. Say no if"
echo "you only want SuperSID recording for now, you can install them later"
echo "with the command printed at the end."
echo ""

EXTRAS_OK="no"
if yes_no "Install them now?" "y"; then
    pip install reportlab astral reverse_geocoder tqdm

    # All three extras are needed. Plain sunpy, or sunpy[net] on its own, gives
    # you Fido but not TimeSeries: importing sunpy.timeseries reaches through
    # sunpy.visualization into mpl_animators and stops with ModuleNotFoundError,
    # and reading the GOES files then needs cdflib, h5netcdf and h5py.
    pip install "sunpy[net,timeseries,visualization]"

    echo ""
    echo "Checking that each script can import what it needs. This is the step"
    echo "that catches a missing package now instead of at 00:02 UTC."
    echo ""

    EXTRAS_OK="yes"

    if python3 -c "from reportlab.platypus import SimpleDocTemplate" >/dev/null 2>&1; then
        echo "  ok     $VLF_SCRIPT"
    else
        echo "  FAILED $VLF_SCRIPT, reportlab is missing"
        EXTRAS_OK="no"
    fi

    if python3 -c "
import pandas, matplotlib
from astral.sun import sun
import reverse_geocoder
" >/dev/null 2>&1; then
        echo "  ok     $HOURLY_SCRIPT"
    else
        echo "  FAILED $HOURLY_SCRIPT"
        EXTRAS_OK="no"
    fi

    if python3 -c "
from sunpy.net import Fido, attrs
from sunpy.timeseries import TimeSeries
import tqdm
" >/dev/null 2>&1; then
        echo "  ok     $DAILY_SCRIPT"
    else
        echo "  FAILED $DAILY_SCRIPT, sunpy is missing an extra"
        EXTRAS_OK="no"
    fi

    if [ "$EXTRAS_OK" = "no" ]; then
        echo ""
        echo "Something did not import. SuperSID itself is unaffected and will"
        echo "record normally, only the plots are held up. The exact command to"
        echo "retry is printed at the end of this install."
    fi
else
    echo "Skipped. The plot scripts will not run until these are installed."
fi


# ---------------------------------------------------------------------------
# 6. where are you
# ---------------------------------------------------------------------------

title "6. Station coordinates and UTC offset"

echo "Looking up your approximate position from your IP address. This fills in"
echo "latitude, longitude, utc_offset and time_zone, and it also decides which"
echo "transmitters are closest to you in step 11."
echo ""
echo "An IP lookup is accurate to the city at best. Check the numbers, and if"
echo "they look wrong, right click your antenna in Google Maps: the first"
echo "number in the popup is latitude, the second is longitude."
echo ""

LATITUDE=""
LONGITUDE=""
UTC_OFFSET=""
TIME_ZONE=""

GEO_JSON=$(curl -s --max-time 10 https://ipapi.co/json/ 2>/dev/null || true)
if ! echo "$GEO_JSON" | grep -q "latitude"; then
    GEO_JSON=$(curl -s --max-time 10 http://ip-api.com/json/ 2>/dev/null || true)
fi

if [ -n "$GEO_JSON" ]; then
    GEO_LINE=$(echo "$GEO_JSON" | python3 -c '
import json, sys
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
lat = d.get("latitude", d.get("lat", ""))
lon = d.get("longitude", d.get("lon", ""))
tz  = d.get("timezone", "")
if isinstance(tz, dict):
    tz = tz.get("id", "")
off = d.get("utc_offset", "")
if not off and "offset" in d:
    s = int(d["offset"])
    sign = "+" if s >= 0 else "-"
    s = abs(s)
    off = "%s%02d%02d" % (sign, s // 3600, (s % 3600) // 60)
if len(off) == 5 and ":" not in off:
    off = off[:3] + ":" + off[3:]
print("%s|%s|%s|%s" % (lat, lon, off, tz))
' || true)

    LATITUDE=$(echo "$GEO_LINE" | cut -d"|" -f1)
    LONGITUDE=$(echo "$GEO_LINE" | cut -d"|" -f2)
    UTC_OFFSET=$(echo "$GEO_LINE" | cut -d"|" -f3)
    TIME_ZONE=$(echo "$GEO_LINE" | cut -d"|" -f4)
fi

# fall back to what the machine itself thinks
if [ -z "$UTC_OFFSET" ]; then
    UTC_OFFSET=$(date +%z | sed 's/\(..\)$/:\1/')   # +0200 becomes +02:00
fi
if [ -z "$TIME_ZONE" ]; then
    TIME_ZONE=$(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo "UTC")
fi

if [ -z "$LATITUDE" ]; then
    echo "The lookup did not work, so there is nothing to press Enter on."
    echo "Type your coordinates in decimal degrees."
    echo ""
fi

LATITUDE=$(ask_needed "Latitude, north is positive" "$LATITUDE")
LONGITUDE=$(ask_needed "Longitude, east is positive" "$LONGITUDE")
UTC_OFFSET=$(ask_needed "UTC offset" "$UTC_OFFSET")
TIME_ZONE=$(ask_needed "Time zone name" "$TIME_ZONE")

echo ""
echo "SuperSID always timestamps in UTC. These two only go into the file"
echo "headers so other people know where the station is."


# ---------------------------------------------------------------------------
# 7. monitor identification
# ---------------------------------------------------------------------------

title "7. Monitor identification"

echo "site_name and contact are mandatory, SuperSID refuses to start without"
echo "them. monitor_id only matters if you run two monitors at one site."
echo ""

SITE_NAME=$(ask_required "Site name, for example CAIRO or ATHENS_ROOF")
MONITOR_ID=$(ask "Monitor id" "${SITE_NAME}_1")
CONTACT=$(ask_required "Contact email or phone")


# ---------------------------------------------------------------------------
# 8. viewer
# ---------------------------------------------------------------------------

title "8. Viewer"

echo "  1) text   console only, one line per reading, no window. This is the"
echo "            one to pick. It works over SSH, on a headless box, and it"
echo "            is the only one that works when cron starts SuperSID at"
echo "            boot, because there is no screen for a window to open on."
echo ""
echo "  2) tk     graphical window with the live spectrum and a vertical line"
echo "            per transmitter. Needs a desktop session on the machine"
echo "            itself, so it cannot be started at boot by cron."
echo ""

VIEWER_CHOICE=$(ask "Viewer (type a number)" "1")
if [ "$VIEWER_CHOICE" = "2" ]; then
    VIEWER="tk"
else
    VIEWER="text"
fi
echo "viewer = $VIEWER"


# ---------------------------------------------------------------------------
# 9. sound card
# ---------------------------------------------------------------------------

title "9. Sound card"

echo "Listing every PCM that alsaaudio can see. Your external card is usually"
echo "the one that is not called PCH, HDMI or Generic. A cheap USB card often"
echo "shows up literally as Device, which looks odd but is normal."
echo ""

DEV_LIST=$(mktemp)
cd "$APP_DIR/src"

# find_alsa_devices.py insists on reading a config file, so point it at the
# one that came with the repository. Ours does not exist yet at this stage.
if [ -f "$SHIPPED_CFG" ]; then
    python3 -u find_alsa_devices.py -l -c "$SHIPPED_CFG" 2>&1 | tee "$DEV_LIST" || true
else
    python3 -u find_alsa_devices.py -l 2>&1 | tee "$DEV_LIST" || true
fi

echo ""

DEVICES=()
while read -r line; do
    DEVICES+=("$line")
done < <(grep -oE '(plug)?hw:CARD=[^, ]+,DEV=[0-9]+' "$DEV_LIST" | sort -u -r)

AUDIO_DEVICE=""

if [ "${#DEVICES[@]}" -eq 0 ]; then
    echo "No capture device was detected. Plug the card in, check 'arecord -l'"
    echo "in another terminal, then type the name in the form"
    echo "plughw:CARD=Device,DEV=0"
    AUDIO_DEVICE=$(ask_required "Device")
else
    echo "Pick the device to record from:"
    echo ""
    i=1
    for d in "${DEVICES[@]}"; do
        printf "  %2d) %s\n" "$i" "$d"
        i=$((i + 1))
    done
    echo "   m) none of these, let me type it myself"
    echo ""
    echo "plughw lets ALSA convert the rate and format for you, hw does not."
    echo "Start with a plughw entry."
    echo ""

    while [ -z "$AUDIO_DEVICE" ]; do
        CHOICE=$(ask "Device (type a number, or m)" "1")
        if [ "$CHOICE" = "m" ] || [ "$CHOICE" = "M" ]; then
            AUDIO_DEVICE=$(ask_required "Device")
        elif is_number "$CHOICE" && [ "$CHOICE" -ge 1 ] && [ "$CHOICE" -le "${#DEVICES[@]}" ]; then
            AUDIO_DEVICE="${DEVICES[$((CHOICE - 1))]}"
        else
            echo "  Type one of the numbers above, or the letter m."
        fi
    done
fi

echo ""
echo "Device = $AUDIO_DEVICE"

CARD_KEY=$(echo "$AUDIO_DEVICE" | sed 's/^plughw://; s/^hw://')
CARD_RATES=$(awk -v key="$CARD_KEY" 'index($0, key) && $0 !~ /hw:/ {f=1; next} f && /rates:/ {print; exit}' "$DEV_LIST" | sed 's/^[[:space:]]*//' || true)
CARD_FORMATS=$(awk -v key="$CARD_KEY" 'index($0, key) && $0 !~ /hw:/ {f=1; next} f && /formats:/ {print; exit}' "$DEV_LIST" | sed 's/^[[:space:]]*//' || true)

# 96000 reaches every transmitter up to 48 kHz and is lighter than 192000
SUGGESTED_RATE="96000"
if [ -n "$CARD_RATES" ]; then
    echo "Card reports: $CARD_RATES"
    if ! echo "$CARD_RATES" | grep -q "96000"; then
        echo ""
        echo "96000 is not in that list. Through plughw ALSA will resample for"
        echo "you, but a rate the card really supports gives cleaner data."
        if echo "$CARD_RATES" | grep -q "192000"; then
            SUGGESTED_RATE="192000"
        else
            SUGGESTED_RATE="48000"
        fi
    fi
fi

SUGGESTED_FORMAT="S32_LE"
if [ -n "$CARD_FORMATS" ]; then
    echo "Card reports: $CARD_FORMATS"
    if ! echo "$CARD_FORMATS" | grep -q "S32_LE"; then
        SUGGESTED_FORMAT="S16_LE"
    fi
fi

echo ""

while true; do
    SAMPLING_RATE=$(ask "audio_sampling_rate, 48000 or 96000 or 192000" "$SUGGESTED_RATE")
    if is_number "$SAMPLING_RATE" && [ "$SAMPLING_RATE" -ge 8000 ]; then
        break
    fi
    echo "  That is not a usable rate. Try 48000, 96000 or 192000."
done

while true; do
    AUDIO_FORMAT=$(ask "Format, S16_LE or S24_3LE or S32_LE" "$SUGGESTED_FORMAT")
    case "$AUDIO_FORMAT" in
        S16_LE|S24_3LE|S32_LE) break ;;
        *) echo "  SuperSID only accepts S16_LE, S24_3LE or S32_LE." ;;
    esac
done

while true; do
    CHANNELS=$(ask "Channels, 1 is mono and is what you want unless you record two antennas" "1")
    if [ "$CHANNELS" = "1" ] || [ "$CHANNELS" = "2" ]; then
        break
    fi
    echo "  Type 1 or 2."
done

MAX_FREQ=$((SAMPLING_RATE / 2))
echo ""
echo "At $SAMPLING_RATE samples per second you can receive transmitters up to"
echo "$MAX_FREQ Hz. Anything above that is out of reach, whatever the config"
echo "says, and SuperSID refuses to start if you list one."

rm -f "$DEV_LIST"


# ---------------------------------------------------------------------------
# 10. logging parameters
# ---------------------------------------------------------------------------

title "10. Logging"

echo "log_format decides how the data files are laid out:"
echo ""
echo "  sid_format         one file per station, timestamp column plus the"
echo "                     value column. Easiest to read and to plot, and the"
echo "                     format Stanford expects. Recommended."
echo "  sid_extended       same, with microseconds in the timestamp."
echo "  supersid_format    all stations in one file, no timestamp column."
echo "  supersid_extended  all stations in one file with a full timestamp."
echo "  both               sid_format plus supersid_format."
echo "  both_extended      sid_extended plus supersid_extended."
echo ""
echo "Pick one of the supersid_* or both* ones if you later switch on"
echo "automatic FTP upload to Stanford."
echo ""

LOG_FORMAT=$(ask "log_format" "sid_format")

echo ""
echo "log_type raw writes the samples exactly as captured. filtered runs them"
echo "through bema_wing first, which smooths the curve. Raw loses nothing,"
echo "since sidfile.py can smooth a raw file afterwards, but filtered is the"
echo "usual choice."
echo ""

LOG_TYPE=$(ask "log_type, filtered or raw" "filtered")

echo ""
echo "log_interval is the seconds between two readings. Each reading captures"
echo "one second of sound. 5 is the standard for SID monitoring."
echo ""

LOG_INTERVAL=$(ask "log_interval" "5")

echo ""
echo "scaling_factor multiplies every value before it is written. Leave it at"
echo "1.0 unless you are matching another monitor."
echo ""

SCALING_FACTOR=$(ask "scaling_factor" "1.0")

echo ""
echo "hourly_save writes hourly_current_buffers.raw.ext.YYYY-MM-DD.csv into"
echo "the data folder every hour. Say yes: the hourly plot script reads that"
echo "file, and it also means a power cut costs you one hour at most."
echo ""

if yes_no "Turn hourly_save on?" "y"; then
    HOURLY_SAVE="YES"
else
    HOURLY_SAVE="NO"
fi

echo ""
echo "data_path is where the csv files go. The three python scripts are"
echo "copied into this same folder, because each of them reads the csv files"
echo "sitting next to it."
echo ""

while true; do
    DATA_PATH=$(ask "data_path" "$APP_DIR/Data")
    DATA_PATH="${DATA_PATH/#\~/$HOME}"
    case "$DATA_PATH" in
        /*) break ;;
        *)  echo "  That has to be a full path starting with a slash, so the"
            echo "  cron jobs find it too. For example $APP_DIR/Data" ;;
    esac
done
mkdir -p "$DATA_PATH"


# ---------------------------------------------------------------------------
# 11. transmitters
# ---------------------------------------------------------------------------

title "11. Transmitters to record"

STATION_BLOCK=""
STATION_COUNT=0
STATION_SUMMARY=""

# matplotlib colour names, one per station, reused if you pick more than this
COLORS=(gold b g r c m y k orange navy brown purple teal olive pink crimson darkgreen steelblue salmon indigo)

VLF_JSON="$DATA_PATH/vlf_table.json"

if [ -f "$SELF_DIR/$VLF_SCRIPT" ]; then
    echo "Running $VLF_SCRIPT for your coordinates. It writes vlf_table.json,"
    echo "vlf_table.csv and vlf_table.pdf into your data folder, sorted from"
    echo "the nearest transmitter outwards."
    echo ""

    cp "$SELF_DIR/$VLF_SCRIPT" "$DATA_PATH/$VLF_SCRIPT"

    # its output is dumped to a log rather than the screen, because the script
    # clears the terminal on start and that would wipe this installer's output
    if python3 "$DATA_PATH/$VLF_SCRIPT" --lat "$LATITUDE" --lon "$LONGITUDE" \
            --out "$DATA_PATH" > "$LOG_DIR/vlf_transit.log" 2>&1; then
        echo "Wrote vlf_table.json, vlf_table.csv and vlf_table.pdf"
    else
        echo "It failed, see $LOG_DIR/vlf_transit.log"
        echo "The pdf needs reportlab, which is in the skipped step 5 packages."
    fi
    echo ""
fi

REACHABLE=""
TOO_HIGH=""
REACH_ALL=""
DUPES=""

# one helper does the classifying, and it stays in tools/ so you can re-run it
# later against the same json if you change the sampling rate
cat > "$TOOLS_DIR/pick_stations.py" <<'PY'
"""Classify the transmitters in vlf_table.json against a sampling rate.

Prints one line per transmitter:

    class|call|freq_hz|distance_km|site|note

class is one of:
    ok      usable, this is what goes in the config
    dup     reachable, but a closer station already uses that frequency
    high    above half the sampling rate, out of reach
    nofreq  the transmitter list has no frequency for it

SuperSID treats a repeated frequency or call sign as a fatal config error, so
the closest station wins and the others are reported as dup.
"""
import json
import sys

path = sys.argv[1]
max_freq = int(sys.argv[2])

with open(path) as handle:
    rows = json.load(handle)["stations"]

seen_freq = {}
seen_call = set()

for row in rows:                      # already sorted nearest first
    call = row["call"]
    freq = row.get("freq_hz")
    dist = row["distance_km"]
    site = row["site"]

    if not freq:
        print("nofreq|%s|0|%s|%s|no frequency listed" % (call, dist, site))
    elif freq > max_freq:
        print("high|%s|%d|%s|%s|" % (call, freq, dist, site))
    elif call.lower() in seen_call:
        print("dup|%s|%d|%s|%s|%s" % (call, freq, dist, site, call))
    elif freq in seen_freq:
        print("dup|%s|%d|%s|%s|%s" % (call, freq, dist, site, seen_freq[freq]))
    else:
        seen_freq[freq] = call
        seen_call.add(call.lower())
        print("ok|%s|%d|%s|%s|" % (call, freq, dist, site))
PY

# scan_stations reads $VLF_JSON at $MAX_FREQ and fills the four lists above
scan_stations() {
    local all
    all=$(python3 "$TOOLS_DIR/pick_stations.py" "$VLF_JSON" "$MAX_FREQ")
    REACHABLE=$(echo "$all" | awk -F"|" '$1=="ok"   {print $2"|"$3"|"$4"|"$5}')
    TOO_HIGH=$( echo "$all" | awk -F"|" '$1=="high" {print $2"|"$3"|"$4"|"$5}')
    DUPES=$(    echo "$all" | awk -F"|" '$1=="dup"  {print $2"|"$3"|"$4"|"$6}')
    REACH_ALL=$(echo "$all" | awk -F"|" '$1=="ok"||$1=="dup" {print $2"|"$3"|"$4"|"$5}')
}

if [ -f "$VLF_JSON" ]; then
    scan_stations
fi

if [ -n "$REACHABLE" ]; then

    REACHABLE_COUNT=$(echo "$REACHABLE" | grep -c .)
    HIGH_COUNT=0
    DUP_COUNT=0
    if [ -n "$TOO_HIGH" ]; then
        HIGH_COUNT=$(echo "$TOO_HIGH" | grep -c .)
    fi
    if [ -n "$DUPES" ]; then
        DUP_COUNT=$(echo "$DUPES" | grep -c .)
    fi

    echo "$REACHABLE_COUNT transmitters are usable at $SAMPLING_RATE samples per"
    echo "second, meaning at or below $MAX_FREQ Hz."

    if [ "$DUP_COUNT" -gt 0 ]; then
        echo ""
        echo "$DUP_COUNT more are in range but share a frequency with a closer"
        echo "one, and SuperSID treats two stations on the same frequency as a"
        echo "fatal config error. The closest of each pair is kept:"
        echo ""
        echo "$DUPES" | head -4 | while IFS="|" read -r call freq dist keeper; do
            printf "     %-12s %8s Hz  same frequency as %s\n" "$call" "$freq" "$keeper"
        done
    fi

    if [ "$HIGH_COUNT" -gt 0 ]; then
        echo ""
        echo "$HIGH_COUNT sit above $MAX_FREQ Hz and are out of reach. The nearest:"
        echo ""
        echo "$TOO_HIGH" | head -4 | while IFS="|" read -r call freq dist site; do
            printf "     %-12s %8s Hz  %9s km  %s\n" "$call" "$freq" "$dist" "$site"
        done

        # anything at or under 96000 Hz comes within reach at 192000
        FIXABLE=$(echo "$TOO_HIGH" | awk -F"|" '$2 <= 96000' | grep -c . || true)
        if [ "$FIXABLE" -gt 0 ] && [ "$SAMPLING_RATE" -lt 192000 ]; then
            echo ""
            echo "$FIXABLE of those would come within reach at 192000 samples per"
            echo "second, at the cost of double the CPU and disk. Your card has"
            echo "to support it, otherwise plughw resamples."
            echo ""
            if yes_no "Raise audio_sampling_rate to 192000?" "n"; then
                SAMPLING_RATE=192000
                MAX_FREQ=96000
                scan_stations
                REACHABLE_COUNT=$(echo "$REACHABLE" | grep -c .)
                echo "audio_sampling_rate is now 192000, $REACHABLE_COUNT usable."
            fi
        fi
    fi

    echo ""
    echo "The nearest ones you can actually record:"
    echo ""
    printf "     %-12s %11s %11s  %s\n" "STATION" "FREQ" "DISTANCE" "SITE"
    echo "$REACHABLE" | head -10 | while IFS="|" read -r call freq dist site; do
        printf "     %-12s %8s Hz %9s km  %s\n" "$call" "$freq" "$dist" "$site"
    done
    echo ""
    echo "How many do you want in the config?"
    echo ""
    echo "  1) the 10 closest"
    echo "  2) the 20 closest"
    echo "  3) type the call signs myself"
    echo "  4) none for now, I will edit the config later"
    echo ""
    echo "More stations is not more work for the machine, one recording is"
    echo "measured at every frequency. With log_format = sid_format you get one"
    echo "csv file per station per day."
    echo ""

    PICKED=""
    while [ -z "$PICKED" ]; do
        HOWMANY=$(ask "Choice (type a number)" "1")
        case "$HOWMANY" in
            1) PICKED=$(echo "$REACHABLE" | head -10) ;;
            2) PICKED=$(echo "$REACHABLE" | head -20) ;;
            3)
                echo ""
                echo "Type the call signs separated by spaces, for example:"
                echo "  NSY GQD DHO38 NAA"
                echo "They are matched against vlf_table.csv in your data folder."
                echo ""
                WANTED=$(ask_required "Call signs")
                PICKED=""
                USED_FREQS=""
                for want in $WANTED; do
                    HIT=$(echo "$REACH_ALL" | awk -F"|" -v w="$want" 'tolower($1)==tolower(w)' | head -1)
                    if [ -z "$HIT" ]; then
                        BAD=$(echo "$TOO_HIGH" | awk -F"|" -v w="$want" 'tolower($1)==tolower(w)' | head -1)
                        if [ -n "$BAD" ]; then
                            BADFREQ=$(echo "$BAD" | cut -d"|" -f2)
                            echo "  $want is at $BADFREQ Hz, above $MAX_FREQ Hz. Left out."
                        else
                            echo "  $want is not in the transmitter list. Left out."
                        fi
                        continue
                    fi
                    HITFREQ=$(echo "$HIT" | cut -d"|" -f2)
                    if echo "$USED_FREQS" | grep -qw "$HITFREQ"; then
                        echo "  $want is on $HITFREQ Hz, which you already picked. Left out."
                        continue
                    fi
                    USED_FREQS="$USED_FREQS $HITFREQ"
                    PICKED="${PICKED}${HIT}
"
                done
                PICKED=$(echo "$PICKED" | grep . || true)
                if [ -z "$PICKED" ]; then
                    echo "  Nothing usable matched, try again."
                fi
                ;;
            4) PICKED="none" ;;
            *) echo "  Type 1, 2, 3 or 4." ;;
        esac
    done

    if [ "$PICKED" != "none" ]; then
        echo ""
        echo "Going into the config:"
        echo ""
        while IFS="|" read -r call freq dist site; do
            [ -z "$call" ] && continue
            COLOR="${COLORS[$((STATION_COUNT % ${#COLORS[@]}))]}"
            STATION_BLOCK="${STATION_BLOCK}
[STATION]
call_sign = $call
color = $COLOR
frequency = $freq
channel = 0
"
            printf "     %-12s %8s Hz  %-10s %s km\n" "$call" "$freq" "$COLOR" "$dist"
            STATION_COUNT=$((STATION_COUNT + 1))
        done <<< "$PICKED"
        STATION_SUMMARY="$STATION_COUNT transmitters"
    fi

else
    # no json, either vlf_transit.py is missing or it failed
    echo "No transmitter list available, so they go in by hand."
    echo ""
    echo "frequency is in Hz, so 45.9 kHz is written 45900, and it has to be"
    echo "at or below $MAX_FREQ Hz at your sampling rate."
    echo "color is any matplotlib colour: gold, b, k, r, g, m, c."
    echo ""

    if yes_no "Add a station now?" "y"; then
        while true; do
            CALL_SIGN=$(ask_required "Call sign, for example NSY")

            FREQUENCY=""
            while [ -z "$FREQUENCY" ]; do
                FREQUENCY=$(ask_required "Frequency in Hz, for example 45900")
                if ! is_number "$FREQUENCY"; then
                    echo "  Numbers only, in Hz. 45.9 kHz is written 45900."
                    FREQUENCY=""
                elif [ "$FREQUENCY" -gt "$MAX_FREQ" ]; then
                    NEEDED=$((FREQUENCY * 2))
                    echo ""
                    echo "  $FREQUENCY Hz needs audio_sampling_rate of at least"
                    echo "  $NEEDED. Yours is $SAMPLING_RATE, and SuperSID refuses"
                    echo "  to start when a station sits above half the rate."
                    echo ""
                    if yes_no "  Raise audio_sampling_rate to $NEEDED?" "y"; then
                        SAMPLING_RATE="$NEEDED"
                        MAX_FREQ=$((SAMPLING_RATE / 2))
                        echo "  audio_sampling_rate is now $SAMPLING_RATE."
                    else
                        echo "  Type a frequency at or below $MAX_FREQ instead."
                        FREQUENCY=""
                    fi
                    echo ""
                fi
            done

            COLOR=$(ask "Colour" "${COLORS[$((STATION_COUNT % ${#COLORS[@]}))]}")
            CHANNEL=$(ask "Channel, 0 unless Channels is 2" "0")

            STATION_BLOCK="${STATION_BLOCK}
[STATION]
call_sign = $CALL_SIGN
color = $COLOR
frequency = $FREQUENCY
channel = $CHANNEL
"
            STATION_COUNT=$((STATION_COUNT + 1))
            echo ""
            if ! yes_no "Add another station?" "n"; then
                break
            fi
            echo ""
        done
        STATION_SUMMARY="$STATION_COUNT transmitters"
    fi
fi

if [ "$STATION_COUNT" -eq 0 ]; then
    STATION_BLOCK="
# No station configured yet. SuperSID starts without one but records nothing
# useful. Copy this block, remove the # marks and put in your transmitter.
# vlf_table.csv in your data folder lists the ones nearest to you.
#
# [STATION]
# call_sign = NSY
# color = gold
# frequency = 45900
# channel = 0
"
    STATION_SUMMARY="none yet"
fi


# ---------------------------------------------------------------------------
# 12. write the config file
# ---------------------------------------------------------------------------

title "12. Writing the config file"

# timestamped, so running this script again never eats stations you added later
if [ -f "$CFG_FILE" ]; then
    BACKUP="$CFG_FILE.$(date -u '+%Y%m%d-%H%M%S').backup"
    cp "$CFG_FILE" "$BACKUP"
    echo "Previous config saved as $BACKUP"
fi

cat > "$CFG_FILE" <<EOF
# SuperSID configuration
# Written by install_supersid.sh on $(date -u '+%Y-%m-%d %H:%M:%S') UTC
# Every line starting with # is a comment.

[PARAMETERS]
# text = console output, tk = graphical window
viewer = $VIEWER

site_name = $SITE_NAME
monitor_id = $MONITOR_ID
contact = $CONTACT

# coordinates of your station in decimal degrees
longitude = $LONGITUDE
latitude = $LATITUDE
utc_offset = $UTC_OFFSET
time_zone = $TIME_ZONE

# samples per second. Highest transmitter you can reach is half of this.
audio_sampling_rate = $SAMPLING_RATE

# seconds between two readings
log_interval = $LOG_INTERVAL

log_format = $LOG_FORMAT
log_type = $LOG_TYPE
scaling_factor = $SCALING_FACTOR

# write a recovery file every hour, the hourly plot script reads it
hourly_save = $HOURLY_SAVE

# absolute path, so the cron jobs find it too
data_path = $DATA_PATH

paper_size = A4
$STATION_BLOCK
[Capture]
Audio = alsaaudio
Device = $AUDIO_DEVICE
Format = $AUDIO_FORMAT
PeriodSize = 1024
Channels = $CHANNELS

[FTP]
automatic_upload = no
ftp_server = sid-ftp.stanford.edu
ftp_directory = /incoming/SuperSID/NEW/
local_tmp = ../outgoing
call_signs =
EOF

echo "Config written to $CFG_FILE"


# ---------------------------------------------------------------------------
# 13. plotting scripts and launchers
# ---------------------------------------------------------------------------

title "13. Plotting scripts"

for f in "$DAILY_SCRIPT" "$HOURLY_SCRIPT" "$RETRY_SCRIPT"; do
    if [ -f "$SELF_DIR/$f" ]; then
        cp "$SELF_DIR/$f" "$DATA_PATH/$f"
        chmod +x "$DATA_PATH/$f"
        echo "Copied $f into $DATA_PATH"
    fi
done

echo ""
echo "They live in the data folder because each one reads the csv files"
echo "sitting next to it. $DAILY_SCRIPT writes into"
echo "$DATA_PATH/output, and $HOURLY_SCRIPT writes into"
echo "$DATA_PATH/hourly_output."
echo ""

# one pane per program, so tmux runs a plain script instead of a long quoted
# command line. Each pane waits at the end, so a crash stays readable.
cat > "$TOOLS_DIR/pane_supersid.sh" <<EOF
#!/bin/bash
cd "$APP_DIR/src" || exit 1
source "$VENV_DIR/bin/activate"
python3 -u supersid.py -c "$CFG_FILE"
echo ""
echo "SuperSID stopped. This pane stays open so you can read any message."
read -r -p "Press Enter to close it > " _
EOF

cat > "$TOOLS_DIR/pane_hourly.sh" <<EOF
#!/bin/bash
# The hourly plot script schedules itself, it sleeps until a couple of minutes
# past each hour and then redraws. That is why it is not a cron job.
cd "$DATA_PATH" || exit 1
source "$VENV_DIR/bin/activate"
export TZ=UTC

if [ ! -f "$DATA_PATH/$HOURLY_SCRIPT" ]; then
    echo "$HOURLY_SCRIPT is not in $DATA_PATH"
    read -r -p "Press Enter to close > " _
    exit 1
fi

# stdin comes from /dev/null on purpose. The script offers to plot one station
# when the file holds several, and with no keyboard attached that question
# would block forever at boot. Reading end of file makes it plot all of them.
python3 -u "$HOURLY_SCRIPT" < /dev/null
echo ""
echo "Hourly plotter stopped."
read -r -p "Press Enter to close it > " _
EOF

# starts the pair in a tmux session, or attaches if it is already running.
# Works from cron too: without a terminal it just leaves the session detached.
cat > "$TOOLS_DIR/run_supersid.sh" <<EOF
#!/bin/bash
SESSION="$SESSION"

if ! command -v tmux >/dev/null 2>&1; then
    echo "tmux is not installed, running SuperSID on its own instead."
    exec "$TOOLS_DIR/pane_supersid.sh"
fi

if ! tmux has-session -t "\$SESSION" 2>/dev/null; then
    tmux new-session -d -s "\$SESSION" -n monitor "$TOOLS_DIR/pane_supersid.sh"
    tmux split-window -h -t "\$SESSION:monitor" "$TOOLS_DIR/pane_hourly.sh"
    tmux select-layout -t "\$SESSION:monitor" even-horizontal
    sleep 1
fi

if [ -t 0 ]; then
    tmux attach-session -t "\$SESSION"
else
    echo "Session '\$SESSION' is running detached. See it with: tmux attach -t \$SESSION"
fi
EOF

# the daily GOES plots, one shot, meant for cron
cat > "$TOOLS_DIR/plot_daily_goes.sh" <<EOF
#!/bin/bash
#
# Draws the finished days. Started by cron once an hour.
#
# cron on Debian and Ubuntu schedules in local time only. It has no CRON_TZ,
# so there is no way to write "00:02 UTC" in a crontab line. Instead cron runs
# this every hour and the check below does the work in the UTC hour we want and
# returns immediately the other twenty three times. That is correct in every
# time zone and it survives daylight saving changes.
#
#   plot_daily_goes.sh          respect the hour check, this is what cron calls
#   plot_daily_goes.sh --now    run straight away, for testing and for @reboot

RUN_AT_UTC_HOUR="00"

if [ "\$1" != "--now" ] && [ "\$(date -u +%H)" != "\$RUN_AT_UTC_HOUR" ]; then
    exit 0
fi

cd "$DATA_PATH" || exit 1
source "$VENV_DIR/bin/activate"
export TZ=UTC

LOG="$LOG_DIR/plot_daily_goes.log"
SCRIPT="$DATA_PATH/$DAILY_SCRIPT"

if [ ! -f "\$SCRIPT" ]; then
    echo "\$(date -u '+%F %T') UTC: \$SCRIPT is not there, skipping." >> "\$LOG"
    exit 0
fi

echo "\$(date -u '+%F %T') UTC: starting \$SCRIPT" >> "\$LOG"
python3 -u "\$SCRIPT" < /dev/null >> "\$LOG" 2>&1
echo "\$(date -u '+%F %T') UTC: finished" >> "\$LOG"
EOF

chmod +x "$TOOLS_DIR"/*.sh
echo "Launchers written to $TOOLS_DIR"
echo ""
echo "SuperSID and the hourly plotter run side by side in a tmux session"
echo "called '$SESSION', so you can watch both at once. tmux keeps them alive"
echo "when you close the terminal or the SSH connection drops."


# ---------------------------------------------------------------------------
# 14. cron
# ---------------------------------------------------------------------------

title "14. Starting things automatically"

echo "Three separate questions, say no to any of them and you can still start"
echo "everything by hand later."
echo ""

START_AT_BOOT="no"
if [ "$VIEWER" = "text" ]; then
    echo "1. SuperSID and the hourly plotter at boot, in the tmux session."
    echo "   This is what gets your station recording again by itself after a"
    echo "   power cut."
    echo ""
    if yes_no "Start them at boot?" "y"; then
        START_AT_BOOT="yes"
    fi
else
    echo "1. viewer is tk, which needs a desktop session, so SuperSID cannot be"
    echo "   started by cron at boot. Skipping that question."
fi

echo ""
echo "2. $DAILY_SCRIPT at 00:02 UTC every day."
echo "   SuperSID closes the day's files at 00:00 UTC, so two minutes later"
echo "   the previous day is complete and ready to plot. This one needs the"
echo "   internet, it downloads GOES x-ray flux and the flare list."
echo ""

DAILY_CRON="no"
if yes_no "Run the daily plots at 00:02 UTC?" "y"; then
    DAILY_CRON="yes"
fi

DAILY_BOOT="no"
if [ "$DAILY_CRON" = "yes" ]; then
    echo ""
    echo "3. The same daily plots once at every boot, as a catch up. If the"
    echo "   machine was off at 00:02 UTC it missed its slot, and the script"
    echo "   skips any pdf it has already made, so this costs nothing."
    echo ""
    if yes_no "Also run them at boot?" "y"; then
        DAILY_BOOT="yes"
    fi
fi

echo ""

if [ "$START_AT_BOOT" = "yes" ] || [ "$DAILY_CRON" = "yes" ] || [ "$DAILY_BOOT" = "yes" ]; then

    CRON_TMP=$(mktemp)
    crontab -l 2>/dev/null | sed '/# BEGIN SUPERSID/,/# END SUPERSID/d' > "$CRON_TMP" || true

    {
        echo "# BEGIN SUPERSID"
        echo "# written by install_supersid.sh, edit with: crontab -e"
        echo "SHELL=/bin/bash"
        echo "#"
        echo "# cron schedules in local time and Debian cron has no CRON_TZ, so the"
        echo "# daily job runs every hour and plot_daily_goes.sh returns at once"
        echo "# unless the UTC hour is 00. That is right in every time zone."
        if [ "$START_AT_BOOT" = "yes" ]; then
            echo "@reboot sleep 60 && $TOOLS_DIR/run_supersid.sh"
        fi
        if [ "$DAILY_CRON" = "yes" ]; then
            echo "2 * * * * $TOOLS_DIR/plot_daily_goes.sh"
        fi
        if [ "$DAILY_BOOT" = "yes" ]; then
            echo "@reboot sleep 180 && $TOOLS_DIR/plot_daily_goes.sh --now"
        fi
        echo "# END SUPERSID"
    } >> "$CRON_TMP"

    crontab "$CRON_TMP"
    rm -f "$CRON_TMP"

    sudo systemctl enable cron >/dev/null 2>&1 || true
    sudo systemctl start cron >/dev/null 2>&1 || true

    echo "Installed. Your SuperSID lines are now:"
    echo ""
    crontab -l | sed -n '/# BEGIN SUPERSID/,/# END SUPERSID/p'
    echo ""
    echo "The daily line fires every hour on purpose. cron can only schedule in"
    echo "local time, and Debian cron ignores CRON_TZ, so the script itself"
    echo "checks the UTC hour and exits in a few milliseconds twenty three times"
    echo "a day. Test it any time with:"
    echo ""
    echo "  $TOOLS_DIR/plot_daily_goes.sh --now"
    echo ""
    echo "Your machine is on $(timedatectl show -p Timezone --value 2>/dev/null || cat /etc/timezone 2>/dev/null || echo 'an unknown zone')."
    echo "Many operators put the whole station on UTC so that logs and clocks"
    echo "match the data. That is optional and nothing here depends on it."
    echo ""
    if yes_no "Set this machine's time zone to UTC?" "n"; then
        sudo timedatectl set-timezone UTC && echo "Machine is now on UTC."
    fi
else
    echo "Nothing added to cron. The launchers in $TOOLS_DIR still work by hand."
fi


# ---------------------------------------------------------------------------
# 15. bash alias
# ---------------------------------------------------------------------------

title "15. Bash alias"

echo "An alias so one word opens the tmux session with SuperSID on the left"
echo "and the hourly plotter on the right. Press Enter at the prompt to take"
echo "the name shown, or type your own."
echo ""

ALIAS_NAME=$(ask "Alias name" "supersid")

if [ -n "$ALIAS_NAME" ]; then

    BASHRC="$HOME/.bashrc"
    touch "$BASHRC"

    # drop any previous block, so running this script twice does not stack
    # two copies of the alias in .bashrc
    sed -i '/# BEGIN SUPERSID ALIAS/,/# END SUPERSID ALIAS/d' "$BASHRC"

    cat >> "$BASHRC" <<EOF
# BEGIN SUPERSID ALIAS
# written by install_supersid.sh
red="\033[38;2;205;49;49m"
white="\033[37m"
reset="\033[0m"
alias $ALIAS_NAME='echo -e "\n\${red}($ALIAS_NAME)\${white} opening the monitor session\${reset}\n"; $TOOLS_DIR/run_supersid.sh; echo -e "\n\${red}($ALIAS_NAME)\${white} detached, both programs keep running\${reset}\n"'
alias $ALIAS_NAME-stop='tmux kill-session -t $SESSION 2>/dev/null && echo -e "\n\${red}($ALIAS_NAME)\${white} stopped\${reset}\n" || echo "nothing was running"'
# END SUPERSID ALIAS
EOF

    echo ""
    echo "Added to $BASHRC. Load it into this terminal with:"
    echo ""
    echo "  source ~/.bashrc"
    echo ""
    echo "Then $ALIAS_NAME opens the session and $ALIAS_NAME-stop shuts it down."
    echo ""
    echo "Inside tmux: Ctrl+B then D leaves it running in the background,"
    echo "Ctrl+B then arrow keys move between the two panes."
else
    echo "Skipped."
fi


# ---------------------------------------------------------------------------
# 16. done
# ---------------------------------------------------------------------------

title "Finished"

cat <<EOF
Program      : $APP_DIR
Config       : $CFG_FILE
Data         : $DATA_PATH
Logs         : $LOG_DIR
Transmitters : $STATION_SUMMARY
Sound card   : $AUDIO_DEVICE at $SAMPLING_RATE Hz

Start everything:

  source ~/.bashrc      (once, or just open a new terminal)
  $ALIAS_NAME

That opens tmux with SuperSID on the left and the hourly plotter on the
right. Ctrl+B then D detaches and leaves both running.

In the data folder:

  vlf_table.pdf         transmitters near you, bearings and distances
  force_goes_retry.py   redraw a day now instead of waiting for the retry
  vlf_table.csv         the same as a spreadsheet
  output/               daily plots with GOES x-ray flux
  hourly_output/        the plot of the day so far, redrawn every hour

To add or remove a transmitter, edit the config:

  nano $CFG_FILE

and add one block per transmitter, frequency in Hz and at or below
$MAX_FREQ Hz at your current sampling rate:

  [STATION]
  call_sign = NSY
  color = gold
  frequency = 45900
  channel = 0

Check the sound card again at any time:

  cd $APP_DIR/src
  source $VENV_DIR/bin/activate
  python3 -u find_alsa_devices.py -l

If SuperSID complains about the device, run the same script without -l to
test rates and formats for real. That plays a tone out of the card and
listens for it on the input, so it needs a cable from line out to line in.
EOF

if [ "$EXTRAS_OK" = "no" ]; then
    cat <<EOF

The plotting packages are not fully installed. SuperSID records without them.
When you want the plots:

  source $VENV_DIR/bin/activate
  pip install reportlab astral reverse_geocoder tqdm
  pip install "sunpy[net,timeseries,visualization]"

Then check it worked before waiting for cron:

  $TOOLS_DIR/plot_daily_goes.sh
  tail $LOG_DIR/plot_daily_goes.log
EOF
fi
