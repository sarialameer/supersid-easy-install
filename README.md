# SuperSID easy install

A one-command installer and plotting set for a [SuperSID](https://github.com/sberl/supersid)
VLF monitoring station on Debian based Linux.

**Everything this repo installs belongs to
[github.com/sberl/supersid](https://github.com/sberl/supersid).** This is a
wrapper around it, nothing more. The installer clones that repository and sets
it up. I did not write SuperSID, I do not maintain it, and all the credit for it
goes there.

```bash
cd ~/Downloads
git clone https://github.com/sarialameer/supersid-easy-install.git
cd supersid-easy-install
chmod +x install_supersid.sh
./install_supersid.sh
```

## Why this exists

I put a SuperSID station together by hand, and the install was the hardest part
of it. Not the soldering, not the antenna, the install. The same problems came
back every time I set up another machine:

**Which sound card is mine.** `arecord -l` and `find_alsa_devices.py -l` list
every PCM the kernel knows about, and the one you want is rarely obvious. On
most machines the external USB card shows up literally as `CARD=Device`, because
cheap cards ship without a product name, while `CARD=PCH` is the motherboard
chip you do not want. So `plughw:CARD=Device,DEV=0` is usually the right answer
and it looks like a placeholder somebody forgot to fill in. Getting that one
line wrong gives you a config that starts and records silence.

**Frequencies that quietly break the config.** SuperSID refuses to start if a
station sits above half your sampling rate, and it refuses to start if two
stations share a frequency. Both are fatal errors that name a line number, not
the reason. The second one catches nearly everyone in Europe and Asia, because
the Russian RSDN-20 network transmits on 20500 Hz from several sites at once, so
a straightforward list of the nearest transmitters is a config that will not
start.

**Coordinates, UTC offsets and cron.** Every one of those is easy on its own and
all of them together are an evening.

**Python versions.** The pinned numpy and pandas in `requirements.txt` do not
build on Python 3.12 or later, and the error you get points at a compiler rather
than at a version pin.

Doing all of that by hand is fine once you know it. This script is so that
somebody who is not a Linux person can put a station up without learning any of
it first, on any Debian based distribution: Debian, Ubuntu, Mint, Raspberry Pi
OS, Pop!\_OS, Zorin, MX Linux and the rest.

## About the code and where credit belongs

I built this with a lot of help from AI "BASH". I do not claim to have this much
knowledge on my own, and I am not presenting it as my own work. The parts worth
having, SuperSID itself, are somebody else's:

- **SuperSID** by sberl and contributors, MIT licensed, originally by
  ericgibert: <https://github.com/sberl/supersid>
- The Stanford SOLAR Center, whose SID monitor programme SuperSID was written
  for: <http://solar-center.stanford.edu/SID/sidmonitor/>
- Loudet's SID station pages, which the antenna and station geometry notes lean
  on: <https://sidstation.loudet.org>

If something here is useful, the credit is theirs. If something here is broken,
that part is mine.

## What the installer does

1. Asks where to install, then installs the apt packages: git, curl, cron, tmux,
   alsa-utils, the ALSA headers, the build tools and tkinter.
2. Clones SuperSID from the upstream repository.
3. Creates a Python virtual environment called `supersid` inside it, and unpins
   numpy and pandas so they install on current Python.
4. Installs the plotting packages, then checks that each script can import what
   it needs, so a missing package shows up now and not in a cron log at 00:02.
5. Looks up your coordinates, UTC offset and time zone, and lets you correct
   any of it.
6. Asks for the site name, monitor id and contact.
7. Lists your sound cards and reads back what each one really supports, so it
   can warn you if you pick a rate the card does not have.
8. Explains every logging option as it asks: `log_format` with all six values,
   `log_type`, `log_interval`, `hourly_save`, `scaling_factor`.
9. Runs `vlf_transit.py` for your position and offers the 10 nearest
   transmitters, the 20 nearest, a list you type yourself, or none. It removes
   the ones your sampling rate cannot reach and the ones that would collide on a
   frequency, and tells you which and why.
10. Writes `Config/supersid.cfg`, backing up whatever was there.
11. Copies the three python scripts into your data folder and writes the tmux
    launchers.
12. Sets up cron, if you want it, and a bash alias.

Every question shows what pressing Enter will do:

```
audio_sampling_rate, 48000 or 96000 or 192000 [Enter = 96000] > 
Site name, for example CAIRO or ATHENS_ROOF (required, cannot be empty) > 
Turn hourly_save on? (y/n) [Enter = y] > 
Alias name [Enter = supersid] > 
```

## What you get

```
~/projects/supersid/
  src/                       SuperSID itself, from the upstream repo
  Config/supersid.cfg        written for you
  supersid/                  the virtual environment
  Data/                      your csv files and the three scripts
    vlf_transit.py
    plotting_stations_goes.py
    plotting_hourly_update.py
    force_goes_retry.py
    vlf_table.json .csv .pdf   transmitters near you, with bearing and distance
    output/2026-08-18/         daily plots, one folder per date
    hourly_output/              the running day, redrawn every hour
  tools/                     launchers and the station picker
  logs/
```

Type `supersid` and a tmux session opens with SuperSID recording on the left and
the hourly plotter on the right. Ctrl+B then D detaches and leaves both running,
`supersid-stop` shuts them down.

## The three scripts

**`vlf_transit.py`** takes your coordinates and works out the bearing, the great
circle distance and the solar noon for every VLF transmitter it knows, then
writes the table as json, csv and pdf. The installer reads the json to build
your station list. The maths is in `docs/vlf_reception_notes.pdf`.

**`plotting_stations_goes.py`** draws the finished days: GOES x-ray flux on top,
your recorded signal underneath exactly as it sits in the file, with sunrise,
sunset, solar noon and the SWPC flare list marked. One pdf per station per day,
in a folder named after the date. If NOAA has not published the flux yet, the
plot says so and is redrawn automatically each day until the flux appears.

**`force_goes_retry.py`** does that redraw now instead of waiting a day. Run it
with no arguments to see which dates are still missing their flux.

**`plotting_hourly_update.py`** redraws the day in progress every hour from the
`hourly_save` buffer. Two panels per station: the BEMA filtered signal on top
and a ten minute moving average underneath. It applies SuperSID's BEMA filter
itself, because the hourly dump is always written raw regardless of what
`log_type` says. There is a section about that in
`docs/vlf_reception_notes.pdf`.

The hourly plots sit directly in `hourly_output/`, not in date folders, because
each round overwrites the same file. When the date rolls over the previous day's
plots are deleted, since the daily script keeps the finished version of that
day.

## Things worth knowing before you start

**You need an external sound card.** The motherboard input will not do it. The
card sets the ceiling: at 96000 samples per second you can receive transmitters
up to 48 kHz, which covers almost everything worth recording.

**Pick `text`, not `tk`, unless the machine has a screen you sit in front of.**
The graphical viewer cannot start from cron at boot, because there is no display
to open a window on.

**Above 48.5 degrees of latitude** the plots leave out astronomical dawn and
dusk in midsummer and say so on the figure, because at that latitude there is no
astronomical darkness to mark. Nothing breaks, it is just honest about it.

**The daily plots need the internet.** GOES flux and the flare list are
downloaded per day.

## Documentation

- `docs/SUPERSID_INSTALL_NOTES.md` explains every command the installer runs,
  every config key, the cron syntax and the troubleshooting.
- `docs/vlf_reception_notes.pdf` covers the loop antenna voltage, the azimuth
  and great circle formulas behind `vlf_transit.py`, and why the hourly figure
  says the filtering was applied by the plotting script. Source in
  `vlf_reception_notes.tex`, build with `pdflatex`.

For anything about SuperSID itself, read the upstream documentation, which is
better than anything I could write about it:
<https://github.com/sberl/supersid/tree/master/docs>

## License

MIT, matching upstream. SuperSID is MIT, copyright 2013 ericgibert. This
repository does not redistribute it, the installer clones it from source.

## Credit

All of it goes to <https://github.com/sberl/supersid>.
