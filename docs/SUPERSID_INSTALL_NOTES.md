# SuperSID install notes

Companion to `install_supersid.sh`. Every command the script runs is explained
here, then the config file key by key, then the transmitter list, tmux and cron.

You can also work straight down this file and type the commands yourself. The
script does them in order and asks you the questions.

## What goes where

Put these four files in one folder before you start:

```
install_supersid.sh
vlf_transit.py
plotting_stations_goes.py
plotting_hourly_update.py
```

The last one was called `plotting_sid_goesfig4.py`. Rename it, the installer
looks for the new name. Nothing inside the file changed.

After the install:

```
~/projects/supersid/
  src/                       SuperSID itself
  Config/supersid.cfg        the config the installer writes
  supersid/                  the virtual environment
  Data/                      data_path, and the three python scripts
    vlf_transit.py
    plotting_stations_goes.py
    plotting_hourly_update.py
    force_goes_retry.py
    vlf_table.json .csv .pdf   transmitters near you
    output/                    daily plots
    hourly_output/             the running day, redrawn hourly
  tools/                     launchers, written by the installer
  logs/
```

The three python scripts live in the data folder because each one reads the csv
files sitting next to it. `plotting_stations_goes.py` and
`plotting_hourly_update.py` both work out their own folder with
`os.path.dirname(os.path.abspath(__file__))`, so putting them anywhere else
means they find no data.

## Reading the questions

Every prompt ends with a `>`. What comes before it tells you what to do:

`[Enter = something]` means pressing Enter takes that value. Type your own to
replace it.

`(required, cannot be empty)` means there is no default. Pressing Enter just
asks again.

`(y/n) [Enter = y]` means type `y` or `n`. Enter takes the letter shown. Any
answer that does not start with y or Y counts as no.

`(Enter = skip this)` means Enter skips the step on purpose and leaves it out.

`(type a number)` goes with a numbered list printed just above it.

Nothing is written to disk until the questions are finished, so Ctrl+C is safe
at any point up to then.

## Running the script

```bash
chmod +x install_supersid.sh
./install_supersid.sh
```

`chmod +x` sets the execute bit, without it the shell says "Permission denied".
The `./` means "the file in this folder", because the shell searches only the
folders in `$PATH` otherwise.

Run it as your normal user. Do not put `sudo` in front. The script calls `sudo`
itself for apt and nothing else. Running the whole thing as root leaves the
clone, the virtual environment and the data owned by root, and installs the
crontab for root instead of you, so your jobs look like they vanished when you
later check `crontab -l`.

## System packages

```bash
sudo apt update
sudo apt install -y git curl cron tmux alsa-utils libasound2-dev \
    build-essential python3-dev python3-venv python3-tk
```

`apt update` refreshes the list of available packages. It upgrades nothing.
Skipping it is the usual reason apt cannot find a package on a machine that has
been off for a while. `-y` answers the confirmation prompt so the install does
not stop halfway.

`git` downloads the source and pulls updates later.

`curl` fetches the location lookup.

`cron` is the scheduler. Present on most desktops, missing on minimal server
images.

`tmux` keeps SuperSID and the hourly plotter running in two panes, and keeps
them alive when you close the terminal or the SSH link drops.

`alsa-utils` gives `arecord`, `aplay` and `alsamixer`. SuperSID's device finder
calls `arecord` internally to ask the kernel what each card supports, so it is
needed even if you never type it yourself.

`libasound2-dev` is the ALSA header files. `pyalsaaudio` is a C extension that
compiles against them, and without this you get an error about a missing
`alsa/asoundlib.h`.

`build-essential` and `python3-dev` are the compiler and Python headers, needed
for the same reason, since `pyalsaaudio` has no prebuilt Linux wheel.

`python3-venv` provides the `venv` module, which Debian splits out.

`python3-tk` is tkinter, needed only for `viewer = tk`.

## Getting the code

```bash
mkdir -p ~/projects
git clone https://github.com/sberl/supersid.git ~/projects/supersid
```

`mkdir -p` creates parents as needed and stays quiet if the folder exists.
Without `-p` it fails on an existing folder and stops the script.

On a second run the script pulls instead:

```bash
git -C ~/projects/supersid pull --ff-only
```

`-C` means "act as if you were in that folder". `--ff-only` refuses to make a
merge commit, so if you edited a tracked file the pull stops cleanly rather
than making a mess.

## The virtual environment

```bash
python3 -m venv supersid
source supersid/bin/activate
```

This creates a private Python in `~/projects/supersid/supersid/`. The nesting
looks odd but it keeps everything under one directory.

pip installs then land inside that folder instead of the system Python. Nothing
here can break other software, and recent Debian and Ubuntu block pip from
touching the system Python anyway, which is the "externally managed
environment" error.

`source` runs the activate script inside your current shell instead of a child
process. That matters, because the script only sets environment variables and a
child cannot change its parent's variables. Afterwards `python3` and `pip` mean
the venv copies, and the prompt usually shows `(supersid)`.

Leave it with `deactivate`, or by opening a new terminal.

## Python packages

```bash
pip install --upgrade pip
pip install setuptools wheel
```

Newer Python removed `distutils`, and old setuptools cannot build without it.
Doing this first is what avoids the "no module named distutils" and "metadata
generation failed" errors.

```bash
sed -i 's/numpy~=1.23.0/numpy/g' requirements.txt
sed -i 's/pandas~=2.1.0/pandas/g' requirements.txt
pip install -r requirements.txt
```

`sed` is a stream editor, `s/old/new/g` substitutes every occurrence on a line,
and `-i` edits the file in place. `numpy~=1.23.0` pins numpy to 1.23.x, which
has no prebuilt wheel for Python 3.12 or 3.13, so pip tries to compile it and
fails. Without the pin, pip takes the current wheel and installs in seconds.
Running the sed twice changes nothing the second time.

The plotting scripts need five more packages, which the installer offers as one
optional step:

```bash
pip install reportlab astral reverse_geocoder tqdm
pip install "sunpy[net,timeseries,visualization]"
```

`reportlab` writes the pdf table in `vlf_transit.py`. `astral` computes sunrise,
sunset and solar noon. `reverse_geocoder` turns coordinates into a city name
offline. `tqdm` is the progress bar. sunpy is the heavy one, a few hundred MB
with its dependencies.

All three sunpy extras are needed, and picking fewer is a trap. `net` gives you
`Fido`, which downloads the data. `timeseries` gives you `TimeSeries`, which
reads it, and brings `cdflib`, `h5netcdf` and `h5py` for the netCDF and CDF
files GOES data arrives in. `visualization` is not used directly by the script
at all, but `sunpy.timeseries` imports `sunpy.visualization` on the way in,
which reaches `mpl_animators`. Install only `sunpy[net]` and the script dies on
its import line:

```
File "plotting_stations_goes.py", line 22, in <module>
    from sunpy.timeseries import TimeSeries
...
ModuleNotFoundError: No module named 'mpl_animators'
```

`pip install "sunpy[all]"` also works and is easier to remember, at the cost of
pulling in map, image and several other extras this station never touches.

After installing, the script checks that each of the three python files can
import what it needs and prints ok or FAILED for each. That check exists so a
missing package surfaces during the install rather than in a cron log at 00:02
UTC.

Say no if you only want recording for now. The command is printed again at the
end of the install.

## Finding your coordinates and UTC offset

```bash
curl -s --max-time 10 https://ipapi.co/json/
```

`-s` hides the progress meter so the output is clean JSON. `--max-time 10`
gives up instead of hanging. The script tries `ipapi.co`, falls back to
`ip-api.com`, and parses whichever answers. The two name their fields
differently and `ip-api.com` gives the offset in seconds, so 7200 is converted
to `+02:00`.

This is an IP lookup, not GPS. It is right to the city at best and sometimes
lands on your provider's exchange. Check it. Right click your antenna in Google
Maps and the popup gives latitude first, longitude second, in the decimal form
the config wants.

These coordinates do two jobs: they go in the config header, and they decide
which transmitters are nearest to you in the next step.

If the lookup fails the script falls back to the machine itself:

```bash
date +%z                                  # +0200, the current offset
timedatectl show -p Timezone --value      # Africa/Cairo
```

The offset is turned into `+02:00` by `sed 's/\(..\)$/:\1/'`, which captures
the last two characters and puts a colon before them. On systems without
systemd, `cat /etc/timezone` gives the zone name.

None of this changes when data is recorded. SuperSID timestamps in UTC always.
`utc_offset` and `time_zone` only go into the file headers.

## Finding the sound card

```bash
cd ~/projects/supersid/src
source ~/projects/supersid/supersid/bin/activate
python3 -u find_alsa_devices.py -l
```

`-u` is unbuffered output, so lines appear as they happen instead of sitting in
a buffer. `-l` lists what is available and exits.

The names that matter are the `hw:` and `plughw:` ones. `PCH` is the
motherboard chip. A USB card often appears literally as `Device`, because cheap
cards do not set a product name. Yours is whichever is not PCH, HDMI or
Generic. `DEV` is usually 0, but a card with several inputs can use 1 or 2.

`hw:` talks to the hardware directly and fails if you ask for a rate or format
the card does not do. `plughw:` puts ALSA's conversion layer in front and
accepts anything, resampling as needed. Start with `plughw:`.

Under the list, each card reports its real rates and formats. The installer
reads that back and warns you if you chose 96000 on a card that only does 44100
and 48000.

The tool insists on reading a config file first, so the installer points it at
the sample config that ships with the repository, since yours does not exist
yet at that point.

To test for real instead of listing:

```bash
python3 -u find_alsa_devices.py -d CARD=Device
```

That plays a tone out of the card and checks it comes back on the input, for
every rate and format combination, so it needs a loopback cable between line
out and line in. Use `-t CARD=Other` if the tone comes from a different card,
or `-t external,10000` with your own signal generator. `-b` brute forces every
PCM and takes a long time, so leave it unless nothing else worked.

`arecord -l` is the plain ALSA listing and is worth knowing as a cross check.

## The transmitter list

`vlf_transit.py` holds a table of VLF transmitters from Wikipedia with their
coordinates and frequencies. The installer runs it with your coordinates:

```bash
python3 vlf_transit.py --lat 30.0444 --lon 31.2357 --out ~/projects/supersid/Data
```

`--lat` and `--lon` skip its own IP lookup, since the installer already has
your position. It writes three files into the data folder:

`vlf_table.json` is what the installer reads to build the config.

`vlf_table.csv` opens in any spreadsheet. This is the one to look at when
choosing call signs by hand.

`vlf_table.pdf` is the same table on paper, with bearing, distance and solar
noon per transmitter. It needs `reportlab`.

Rows are sorted nearest first. The installer then offers the 10 closest, the 20
closest, typing call signs yourself, or none.

Its output goes to `logs/vlf_transit.log` rather than the screen, because the
script clears the terminal when it starts and that would wipe the installer's
own output.

### Why the list you get is shorter than the list on screen

Three rules cut transmitters out, and two of them are fatal config errors in
SuperSID rather than matters of taste.

**Above half the sampling rate.** You can only receive up to half of
`audio_sampling_rate`. That is the Nyquist limit and SuperSID enforces it. At
96000 the ceiling is 48000 Hz, so SXA at 49000 Hz, DCF77 at 77500 Hz and WWVB
at 60000 Hz are out. The error looks like this:

```
Error: [STATION1:SXA] frequency=49000: audio_sampling_rate=96000 must be >= 98000.
```

The installer counts how many would come back within reach at 192000 and offers
to raise the rate, at the cost of double the CPU and disk.

**Two stations on the same frequency.** This is fatal:

```
Error: [STATION10:RJH99] duplicate 'frequency': '20500'
```

It bites immediately in Europe and Asia, because the Russian RSDN-20 network
transmits on 20500 Hz from several sites at once. RJH63, RJH69, RJH77 and RJH99
are all on that frequency, so a plain list of the ten nearest transmitters
produces a config that refuses to start. The installer keeps the closest of
each frequency and tells you which ones it left out and why. Nothing is lost:
it is the same frequency either way.

**Two stations with the same call sign** is fatal in the same way. Two stations
with the same colour is only a printed warning, and the installer hands out
twenty different colours anyway.

The helper doing this stays in `tools/pick_stations.py`, so you can re-run it
yourself after changing the sampling rate:

```bash
python3 ~/projects/supersid/tools/pick_stations.py \
        ~/projects/supersid/Data/vlf_table.json 48000
```

It prints one line per transmitter, classified `ok`, `dup`, `high` or `nofreq`.

## The config file

Open it any time:

```bash
nano ~/projects/supersid/Config/supersid.cfg
```

Ctrl+O then Enter saves, Ctrl+X exits. Lines starting with `#` are comments.

Any error here is fatal. SuperSID prints one message and exits rather than
starting with bad settings, so if it dies straight after launch, read that
first line. It names the exact key.

### [PARAMETERS]

`viewer` is `text` or `tk`. `text` prints readings to the terminal and opens no
window, which is what you want over SSH, on a headless box, and for anything
started at boot. `tk` opens the live spectrum window with a vertical line per
transmitter, and needs a desktop session on the machine itself. Override for
one run with `python3 supersid.py -v text`.

`site_name` is your station's unique name, mandatory.

`monitor_id` separates two monitors at one site.

`contact` is your email or phone, mandatory, and goes into the file headers.

`longitude` and `latitude` are decimal degrees, east and north positive.

`utc_offset` is written `+02:00`. `time_zone` is a name like `Africa/Cairo`.

`audio_sampling_rate` is samples per second, normally 48000, 96000 or 192000.
The most consequential number in the file, see the Nyquist rule above.

`log_interval` is seconds between readings, default 5. Each reading captures one
second of sound. Smaller values mean bigger files without more real detail about
a flare.

`log_type` is `filtered` or `raw`. `filtered` runs `bema_wing` over the data
first, which smooths the curve. `raw` writes what was captured. Raw loses
nothing, since `sidfile.py` can smooth it later, but `filtered` is the usual
choice.

`scaling_factor` multiplies every value before writing. Leave at `1.0` unless
matching another monitor.

`hourly_save` set to `YES` writes
`hourly_current_buffers.raw.ext.YYYY-MM-DD.csv` every hour.
`plotting_hourly_update.py` reads exactly that file, so the hourly plots need
this on. It also means a power cut costs one hour at most.

`data_path` is where csv files go. The installer insists on a full path starting
with `/`. A relative path is resolved against the `src` folder, which works when
you launch by hand from `src` and quietly writes somewhere unexpected when cron
launches it.

`paper_size` is one of A3, A4, A5, Legal, Letter.

### log_format

`sid_format` writes one file per station: timestamp column counting up in
`log_interval` steps from 00:00:00 UTC, then the value. Easiest to read and to
plot, the format Stanford expects, and what the installer defaults to.

`sid_extended` is the same with microseconds in the timestamp.

`supersid_format` puts all stations in one file, one column each, no timestamp
column. Each line is `log_interval` seconds after the one above.

`supersid_extended` is all stations in one file with a full timestamp column.
This is the default in the sample config that ships with the project.

`both` is `sid_format` plus `supersid_format`. `both_extended` is the extended
pair.

With FTP upload switched on, the format has to be `supersid_format`,
`supersid_extended`, `both` or `both_extended`. SuperSID checks the combination
and refuses to start on `automatic_upload = yes` next to a plain `sid_format`.
Since `both` contains `sid_format`, that is where to go if you want per station
files and the upload together.

### [Capture]

```ini
[Capture]
Audio = alsaaudio
Device = plughw:CARD=Device,DEV=0
Format = S32_LE
PeriodSize = 1024
Channels = 1
```

`Audio` is the recording module, `alsaaudio` on Linux.

`Device` is the PCM name, copied exactly. `CARD=device` and `CARD=Device` are
different to ALSA.

`Format` is `S16_LE`, `S24_3LE` or `S32_LE`, nothing else. 16 bit is enough for
most work, 32 bit gives more headroom above the noise floor. Use what the card
reports.

`PeriodSize` is frames per read, default 1024. Try 512 or 256 if you get
overrun warnings.

`Channels` is 1 for mono. Use 1 unless you really record two antennas.

### [STATION]

One block per transmitter, repeated. The section name stays `[STATION]` every
time, it is not numbered.

```ini
[STATION]
call_sign = NSY
color = gold
frequency = 45900
channel = 0
```

`frequency` is in Hz, so 45.9 kHz is `45900`.

`color` is any matplotlib colour: `b`, `g`, `r`, `c`, `m`, `y`, `k`, or names
like `gold`, `navy`, `crimson`.

`channel` is 0 for the left or only channel. It must be less than `Channels`,
so with `Channels = 1` only 0 is valid. Setting it to 1 gives
`channel=1 must be >= 0 and < 'Channels'=1`, an error that does not obviously
point at the station block.

An older config with `[STATION_1]` and `[STATION_2]` still works but prints a
deprecation notice asking you to rename them.

A config with no stations starts fine and records nothing useful.

## The tmux session

SuperSID and the hourly plotter run side by side in a tmux session called
`supersid`, left pane and right pane. tmux is a terminal multiplexer: the
programs run inside it and keep running when you close the window, log out, or
lose the SSH connection.

The installer writes four launchers into `tools/`:

`pane_supersid.sh` activates the venv and runs `supersid.py`. At the end it
waits for Enter, so if SuperSID exits with an error the pane stays open long
enough to read it.

`pane_hourly.sh` does the same for `plotting_hourly_update.py`.

`run_supersid.sh` creates the session with both panes, or attaches to it if it
is already running. It never creates a second copy.

`plot_daily_goes.sh` runs `plotting_stations_goes.py` once, for cron.

Keys once you are inside, all of them Ctrl+B first, then the second key:

```
Ctrl+B  d            detach, both programs keep running
Ctrl+B  left/right   move between the two panes
Ctrl+B  z            zoom the current pane full screen, again to undo
Ctrl+B  [            scroll back, q leaves scroll mode
```

Useful from outside:

```bash
tmux attach -t supersid          # go back in
tmux list-sessions               # is it running
tmux kill-session -t supersid    # stop both programs
```

### Why the hourly plotter is not a cron job

`plotting_hourly_update.py` schedules itself. It plots, works out how long until
a couple of minutes past the next hour, sleeps that long, then plots again. It
is a program that runs forever, so it belongs in a pane next to SuperSID rather
than in a crontab. Adding it to cron as well would start a second copy every
hour.

`pane_hourly.sh` starts it with stdin from `/dev/null`:

```bash
python3 -u plotting_hourly_update.py < /dev/null
```

That is deliberate. When the csv holds more than one station the script asks
which one to plot, and at boot there is nobody to answer, so it would sit at
that question forever and never draw anything. Reading end of file instead
sends it down its `except EOFError` branch, which plots every station, and that
is what an unattended monitor wants. To pick one station by hand, run it
yourself in the data folder without the redirect.

## Cron

The installer asks three separate yes or no questions and adds only the lines
you agreed to, between markers:

```
# BEGIN SUPERSID
SHELL=/bin/bash
@reboot sleep 60 && /home/you/projects/supersid/tools/run_supersid.sh
2 * * * * /home/you/projects/supersid/tools/plot_daily_goes.sh
@reboot sleep 180 && /home/you/projects/supersid/tools/plot_daily_goes.sh --now
# END SUPERSID
```

The five fields before a command are minute, hour, day of month, month, day of
week. A star means every value.

`2 * * * *` is two minutes past every hour, and the daily job really does run
every hour. The section below says why.

`@reboot` runs once when cron starts after boot. `sleep 60 &&` waits first,
because at that moment the network may not be up and USB devices may not have
settled. The 180 second one gives the daily plots a catch up run if the machine
was switched off at 00:02, and since `plotting_stations_goes.py` skips any pdf
it has already made, that costs nothing.

### Why the daily job runs hourly

Cron schedules in local time. There is no way to write "00:02 UTC" in a crontab
line on Debian or Ubuntu, because their cron has no `CRON_TZ`. Writing
`CRON_TZ=UTC` at the top of a crontab is accepted without complaint and then
ignored, so `2 0 * * *` fires two minutes past your local midnight. On a machine
at UTC+3 that is 21:02 UTC the day before, when the day you wanted is not
finished yet.

The fix is to let cron fire every hour and let the script decide. The top of
`plot_daily_goes.sh` is:

```bash
RUN_AT_UTC_HOUR="00"
if [ "$1" != "--now" ] && [ "$(date -u +%H)" != "$RUN_AT_UTC_HOUR" ]; then
    exit 0
fi
```

Twenty three times a day that exits in about four milliseconds. Once a day, in
the UTC hour you asked for, it does the work. This is right in every time zone
and it survives daylight saving changes, which a fixed local time would not.

Run it at any hour yourself with `--now`, which skips the check:

```bash
~/projects/supersid/tools/plot_daily_goes.sh --now
```

Change `RUN_AT_UTC_HOUR` in that file to pick a different UTC hour.

Putting the whole machine on UTC also works, and makes local time and UTC the
same thing:

```bash
sudo timedatectl set-timezone UTC
```

Because the plot jobs run under cron they get almost no environment: no useful
`PATH`, no virtual environment, and not the folder you expect. That is why cron
calls the wrapper scripts and not python directly. Each wrapper does its own
`cd`, `source` and `export TZ=UTC` first, and appends to a log in `logs/`.

Useful commands:

```bash
crontab -l                      # list what is installed
crontab -e                      # edit it
sudo systemctl status cron      # is the scheduler running
grep CRON /var/log/syslog       # did my job fire
```

The installer deletes anything between its two markers before appending, so a
second run leaves exactly one block and any unrelated cron lines are untouched.

## The bash alias

```bash
red="\033[38;2;205;49;49m"
white="\033[37m"
reset="\033[0m"
alias supersid='echo -e "\n${red}(supersid)${white} opening the monitor session${reset}\n"; ~/projects/supersid/tools/run_supersid.sh; echo -e "\n${red}(supersid)${white} detached, both programs keep running${reset}\n"'
alias supersid-stop='tmux kill-session -t supersid 2>/dev/null && echo "stopped" || echo "nothing was running"'
```

The real file gets absolute paths, since `~` inside single quotes is not always
expanded the way you expect.

Load it into a terminal you already have open, or just open a new one:

```bash
source ~/.bashrc
```

`red`, `white` and `reset` hold ANSI escape sequences. `\033[` starts one,
`38;2;205;49;49m` sets a 24 bit colour by RGB, and `0m` puts everything back.
They are plain shell variables rather than part of the alias because the alias
body is in single quotes.

`echo -e` turns on backslash escapes, which is what makes `\n` a newline and
`\033` an escape character instead of literal text.

`${red}` inside the alias is not expanded when the alias is defined. Alias
expansion is textual: bash stores the body as a string and parses it when you
run it, so the variables are read at that moment. That is why they have to
exist in the shell, and why defining them next to the alias in `.bashrc` works.

Since the alias now attaches to tmux instead of running SuperSID directly, the
closing message prints when you detach, and both programs keep going. That is
the point of tmux, and `supersid-stop` is how you actually stop them.

Note that `red`, `white` and `reset` are ordinary lowercase names. If something
else in your `.bashrc` uses them, one wins and your colours change. Renaming
both the definitions and the references to something like `ss_red` avoids it.

The block sits between `# BEGIN SUPERSID ALIAS` and `# END SUPERSID ALIAS`, and
a second install run replaces it rather than adding a second copy.

## The plotting scripts

`plotting_stations_goes.py` is the daily one. It walks every csv in the data
folder, and for each draws GOES x-ray flux on the top panel and your recorded
signal on the bottom, with sunrise, sunset, solar noon and the SWPC flares
marked. Output goes to `Data/output/` as one pdf per station per day, and it
skips any pdf that already exists, so running it twice is cheap. It needs the
internet for the GOES and flare downloads.

`plotting_hourly_update.py` is the running day. Every hour it re-reads
`hourly_current_buffers.raw.ext.<today>.csv` and redraws each station into
`Data/hourly_output/` under the same file name each time, so the file always
holds everything recorded so far. There are no date folders here, on purpose:
the plot is provisional and gets overwritten every hour. Once the date rolls
over, the previous day's plots are deleted. Nothing is lost, because the
finished version of that day is what the daily script writes into its own output
folder.

Each station gets two panels sharing one x axis. The upper one is the BEMA
filtered signal, the lower one a plain moving average over `MOVING_AVG_MINUTES`,
ten by default.

Every value in the buffer is drawn, zeros included. The buffer holds a slot for
each moment of the day from the start and every slot reads 0 until the monitor
reaches it, so early in the day the curve runs along zero for the part that has
not happened yet. Those zeros are kept because a reading of 0 can also mean the
transmitter was off air, which is worth seeing, and there is no way to tell the
two apart from the file alone. The times in the plot title come from the non
zero part, so it still says how far the recording has got. `PLOT_ZEROS = False`
at the top of the script leaves them out instead. The window is worked out from the `LogInterval` in the file
header rather than assumed, so ten minutes stays ten minutes whatever the log
interval is. At the usual five seconds that is 120 samples, and the panel title
says so. It applies the bema filter itself, controlled by `BEMA_WING` near
the top of the file, because the hourly dump is written raw.

### Which csv files the daily script plots

It plots single station day files and passes over everything else in the data
folder without a word. Two files used to get picked up and fail:

```
Failed on vlf_table.csv: 'UTC_StartTime'
Failed on hourly_current_buffers.raw.ext.2026-08-18.csv: 'StationID'
```

`vlf_table.csv` is the transmitter list and has no `#` header at all.
`hourly_current_buffers...` is the combined dump, which carries `Stations` and
`Frequencies` where the daily script expects `StationID` and `Frequency`. Both
are now filtered out by reading the header first. Set `SHOW_SKIPPED = True` near
the top of the script to see what was passed over and why.

### Where the plots are written

Both scripts write into a folder named after the date:

```
Data/output/2026-08-18/plot_for_[NSY]_2026-08-18.pdf
Data/hourly_output/plot_for_[NSY]_2026-08-18.pdf
```

The daily plots are finished work and are kept per date. The hourly ones are a
snapshot of the day in progress, so they stay flat and are replaced in place.

### What happens when GOES has no data yet

NOAA often publishes the x-ray flux late, so a plot drawn today with no flux is
not final. When that happens the date is written to `Data/output/.goes_retry.json`
with the time of the attempt, and the plot itself says so:

```
no GOES satellite returned 1-8 A data for this date
the flux is often published late, so this plot is not final: it is deleted and
drawn again on the first run more than 24 hours from now, and every day after
that until the flux appears
```

On the first run more than 24 hours later, the whole date folder is deleted and
every station of that day is drawn again. If the flux is there this time, the
date is dropped from the retry list and the plot is never touched again. If it
is still missing, the clock restarts and the same thing happens tomorrow. Change
`RETRY_AFTER_HOURS` at the top of the script to use a different wait.

A date is only ever deleted while it is on that list, so plots that already have
their flux are safe.

To see what is still waiting, or to force a redraw without waiting the 24 hours,
use `force_goes_retry.py` in the data folder:

```bash
cd ~/projects/supersid/Data
source ~/projects/supersid/supersid/bin/activate

python3 force_goes_retry.py                      # what is still waiting
python3 force_goes_retry.py --all                # mark every waiting date due
python3 force_goes_retry.py 2026-08-21           # mark one date due
python3 force_goes_retry.py --clear 2026-08-21   # keep that plot as final
~/projects/supersid/tools/plot_daily_goes.sh --now
```

It only rewrites the timestamps in `.goes_retry.json`. The deleting and
redrawing is still done by `plotting_stations_goes.py` on its next run.

The lower panel of the daily plot is the signal exactly as it sits in the csv,
with no smoothing added by the script. Whether it arrives smoothed is the
monitor's decision: with `log_type = filtered` SuperSID runs BEMA over the whole
day before writing it, and the panel title says which of the two you are looking
at.

### High latitude stations

Above about 48.5 degrees of latitude the sun does not reach 18 degrees below the
horizon around midsummer, so astronomical twilight never happens. `astral`
raises `ValueError` rather than returning a time, and that used to stop the plot
for the whole date. London, Paris, Berlin, Warsaw, Moscow and Vancouver are all
affected in June, and the southern equivalents below -48.5 degrees in December.
Above the polar circles the sun may not rise or set at all.

Each sun event is now requested separately and whatever cannot happen is left
out of the plot, with a line at the bottom saying why:

```
no adawn, adusk marked: this latitude gets no astronomical darkness on this date
no sunrise, sunset marked: the sun does not rise here on this date
```

Sunrise, sunset and solar noon still appear whenever they exist, and solar noon
always exists. During polar night the whole day is shaded, and flares are
dropped from the count because there is no sunlit ionosphere to respond.

Run either by hand from the data folder:

```bash
cd ~/projects/supersid/Data
source ~/projects/supersid/supersid/bin/activate
python3 plotting_stations_goes.py
```

## Troubleshooting

An error naming a config key means that key is wrong. The message gives the
section, the station and what it expected.

"Device or resource busy" means something else holds the sound card, usually
PulseAudio or PipeWire on a USB card. Try the `plughw:` name instead of `hw:`,
or stop the other program.

"No such file or directory" on the device is nearly always a typo in `Device`,
or the card sitting on a different `DEV` number. List them again and copy the
line exactly.

If pip fails building pyalsaaudio, one of `libasound2-dev`, `build-essential`
or `python3-dev` is missing.

If the tk window never appears, you are probably on SSH with no display. Use
`python3 supersid.py -v text` for that session.

If a cron job does not run, check `crontab -l` as the right user, confirm the
wrapper is executable with `ls -l tools/`, and read the logs in `logs/`. Running
the wrapper by hand almost always reproduces the problem.

If the tmux session looks empty or a pane closed instantly, run
`tools/pane_supersid.sh` directly and read the error. The panes wait for Enter
before closing exactly so that message survives.

If a data file is empty or the values never move, the card is recording
silence. Check the input level with `alsamixer`, F4 picks the capture source, M
unmutes.

If `plotting_stations_goes.py` stops with `ModuleNotFoundError: No module named
'mpl_animators'`, or warns that `cdflib`, `h5netcdf` and `h5py` are missing,
sunpy was installed without the `timeseries` and `visualization` extras. Fix it
with:

```bash
source ~/projects/supersid/supersid/bin/activate
pip install "sunpy[net,timeseries,visualization]"
```

Then run the job by hand instead of waiting for cron:

```bash
~/projects/supersid/tools/plot_daily_goes.sh
tail ~/projects/supersid/logs/plot_daily_goes.log
```

A traceback in that log with a working `cd` and venv means cron and the wrapper
are fine and only the packages were wrong.
