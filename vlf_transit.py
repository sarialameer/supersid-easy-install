"""bearings, distances and solar noon for vlf transmitters, offline, no astropy."""

import argparse
import csv
import json
import math
import os
import sys
from datetime import date, datetime

R_EARTH_KM = 6371.0088

# station table from wikipedia "list of vlf transmitters"
# freqs in hz, main frequency first, empty tuple when the wiki cell is blank
# status: listed = first wiki table, gone = demolished table
STATIONS = (
    {"call": "NOV", "site": "Bolotnoye, Russia", "freqs": (11905,), "lat": 55.75611, "lon": 84.447889, "status": "listed"},
    {"call": "KRA", "site": "Poltavskaya, Russia", "freqs": (12649,), "lat": 45.40333, "lon": 38.15806, "status": "listed"},
    {"call": "KOM", "site": "Khabarovsk, Russia", "freqs": (12649,), "lat": 50.07333, "lon": 136.60667, "status": "listed"},
    {"call": "MUR", "site": "Revda, Russia", "freqs": (12649,), "lat": 68.03556, "lon": 34.6833333, "status": "listed"},
    {"call": "ASH", "site": "Seydi, Turkmenistan", "freqs": (12649,), "lat": 39.47111, "lon": 62.71861, "status": "listed"},
    {"call": "OmegaD", "site": "LaMoure, North Dakota, USA", "freqs": (12100,), "lat": 46.365987, "lon": -98.335667, "status": "listed"},
    {"call": "MonteGrande", "site": "Monte Grande, Argentina", "freqs": (17330, 23600), "lat": -34.757502, "lon": -58.509128, "status": "listed"},
    {"call": "HWU", "site": "Rosnay, France", "freqs": (15100, 18300, 21750), "lat": 46.714119, "lon": 1.244309, "status": "listed"},
    {"call": "Ruiselede", "site": "Ruiselede, Belgium", "freqs": (16200, 51250), "lat": 51.08111, "lon": 3.34278, "status": "listed"},
    {"call": "JXN", "site": "Gildeskal, Norway", "freqs": (16400,), "lat": 66.982337, "lon": 13.872471, "status": "listed"},
    {"call": "VTX", "site": "Vijayanarayanam, India", "freqs": (17000,), "lat": 8.387, "lon": 77.752, "status": "listed"},
    {"call": "SAQ", "site": "Grimeton, Sweden", "freqs": (17200,), "lat": 57.113958, "lon": 12.404425, "status": "listed", "note": "alexanderson day only"},
    {"call": "NAA", "site": "Cutler, Maine, USA", "freqs": (24000, 17800), "lat": 44.644506, "lon": -67.284565, "status": "listed"},
    {"call": "RDL", "site": "Krasnodar, Russia", "freqs": (18100,), "lat": 44.77333, "lon": 39.54722, "status": "listed"},
    {"call": "INS", "site": "Vijayanarayanam, India", "freqs": (18200,), "lat": 8.3869497, "lon": 77.7505891, "status": "listed"},
    {"call": "GQD", "site": "Anthorn, Cumbria, UK", "freqs": (19580, 22100), "lat": 54.911683, "lon": -3.278738, "status": "listed"},
    {"call": "NWC", "site": "Exmouth, Australia", "freqs": (19800,), "lat": -21.816325, "lon": 114.16546, "status": "listed"},
    {"call": "ICV", "site": "Tavolara, Sardinia, Italy", "freqs": (20270, 20760), "lat": 40.922889, "lon": 9.732052, "status": "listed"},
    {"call": "RJH69", "site": "Vileyka, Belarus", "freqs": (20500,), "lat": 54.463204, "lon": 26.775827, "status": "listed"},
    {"call": "RJH77", "site": "Archangelsk, Russia", "freqs": (20500,), "lat": 64.360491, "lon": 41.568489, "status": "listed"},
    {"call": "RJH99", "site": "Nizhny Novgorod, Russia", "freqs": (20500,), "lat": 56.171945, "lon": 43.931667, "status": "listed"},
    {"call": "RJH66", "site": "Bishkek, Kyrgyzstan", "freqs": (20500,), "lat": 43.039444, "lon": 73.6125, "status": "listed"},
    {"call": "RAB99", "site": "Khabarovsk, Russia", "freqs": (20500,), "lat": 48.48555, "lon": 134.82333, "status": "listed"},
    {"call": "RJH63", "site": "Martanskaya, Russia", "freqs": (20500,), "lat": 44.77364, "lon": 39.547262, "status": "listed"},
    {"call": "NPM", "site": "Lualualei, Hawaii, USA", "freqs": (21400,), "lat": 21.420382, "lon": -158.153912, "status": "listed"},
    {"call": "GVT", "site": "Skelton, Cumbria, UK", "freqs": (22100,), "lat": 54.731929, "lon": -2.883359, "status": "listed"},
    {"call": "JJI", "site": "Ebino, Japan", "freqs": (22200,), "lat": 32.092247, "lon": 130.829095, "status": "listed"},
    {"call": "DHO38", "site": "Rhauderfehn, Germany", "freqs": (23400,), "lat": 53.087341, "lon": 7.608652, "status": "listed"},
    {"call": "NLK", "site": "Jim Creek, Washington, USA", "freqs": (24800,), "lat": 48.203633, "lon": -121.916828, "status": "listed"},
    {"call": "Mokpo", "site": "Mokpo, South Korea", "freqs": (24100, 25000), "lat": 34.682222, "lon": 126.446944, "status": "listed"},
    {"call": "NML", "site": "LaMoure, North Dakota, USA", "freqs": (25200,), "lat": 46.365987, "lon": -98.335667, "status": "listed"},
    {"call": "TBB", "site": "Bafa, Didim, Turkey", "freqs": (26700,), "lat": 37.40942, "lon": 27.325273, "status": "listed"},
    {"call": "Dimona", "site": "Dimona, Israel", "freqs": (29700, 26000), "lat": 30.975696, "lon": 35.098668, "status": "listed"},
    {"call": "Goedverwacht", "site": "Cape Town, South Africa", "freqs": (), "lat": -33.787289, "lon": 18.694761, "status": "listed"},
    {"call": "TFK", "site": "Grindavik, Iceland", "freqs": (37600,), "lat": 63.850833, "lon": -22.451667, "status": "listed"},
    {"call": "JJY40", "site": "Otakadoyayama, Japan", "freqs": (40000,), "lat": 37.372557, "lon": 140.849007, "status": "listed"},
    {"call": "SRC", "site": "Grimeton, Sweden", "freqs": (40400,), "lat": 57.113958, "lon": 12.404425, "status": "listed"},
    {"call": "SAS2", "site": "Gudinge, Sweden", "freqs": (42500,), "lat": 60.524275, "lon": 18.012192, "status": "listed"},
    {"call": "NAU", "site": "Aguada, Puerto Rico", "freqs": (40750,), "lat": 18.398775, "lon": -67.177486, "status": "listed"},
    {"call": "NSY", "site": "Niscemi, Italy", "freqs": (45900,), "lat": 37.125654, "lon": 14.436325, "status": "listed"},
    {"call": "SXA", "site": "Kato Souli, Greece", "freqs": (49000,), "lat": 38.145186, "lon": 24.019703, "status": "listed"},
    {"call": "NPG", "site": "Dixon, California, USA", "freqs": (55500,), "lat": 38.371505, "lon": -121.775569, "status": "listed"},
    {"call": "LBH", "site": "Gossa, Norway", "freqs": (57700,), "lat": 62.785927, "lon": 6.90083, "status": "listed"},
    {"call": "WWVB", "site": "Fort Collins, Colorado, USA", "freqs": (60000,), "lat": 40.678056, "lon": -105.046944, "status": "listed"},
    {"call": "JJY60", "site": "Haganeyama, Saga, Japan", "freqs": (60000,), "lat": 33.465539, "lon": 130.175516, "status": "listed"},
    {"call": "MSF", "site": "Anthorn, UK", "freqs": (60000,), "lat": 54.91, "lon": -3.28, "status": "listed"},
    {"call": "RomeNavy", "site": "Rome, Italy", "freqs": (65250,), "lat": 41.975452, "lon": 12.359494, "status": "listed", "note": "wiki cell says W, flipped to E or it lands in the atlantic"},
    {"call": "RBU", "site": "Moscow, Russia", "freqs": (66666,), "lat": 55.730481, "lon": 38.152471, "status": "listed"},
    {"call": "RBU2", "site": "Taldom, Russia", "freqs": (66666,), "lat": 56.733333, "lon": 37.663333, "status": "listed"},
    {"call": "BPC", "site": "Pucheng, China", "freqs": (68500,), "lat": 34.948333, "lon": 109.542778, "status": "listed"},
    {"call": "BSF", "site": "Guishan, Taiwan", "freqs": (77500,), "lat": 25.005556, "lon": 121.365, "status": "listed"},
    {"call": "DCF77", "site": "Mainflingen, Germany", "freqs": (77500,), "lat": 50.014234, "lon": 9.011487, "status": "listed"},
    {"call": "Tving", "site": "Tving, Sweden", "freqs": (), "lat": 56.27505, "lon": 15.487858, "status": "listed"},
    {"call": "MKL", "site": "Crimond, UK", "freqs": (82800, 51950), "lat": 57.617467, "lon": -1.887617, "status": "listed"},
    {"call": "GIZ20", "site": "Inskip, UK", "freqs": (61840,), "lat": 53.830074, "lon": -2.834262, "status": "listed"},
    {"call": "FTA2", "site": "Saint Assise, France", "freqs": (16900, 20900), "lat": 48.54491, "lon": 2.576294, "status": "listed"},
    {"call": "FUG", "site": "Villemagne, France", "freqs": (62600,), "lat": 43.386781, "lon": 2.097364, "status": "listed"},
    {"call": "FUE", "site": "Kerlouan, France", "freqs": (62600, 65800), "lat": 48.637736, "lon": -4.350769, "status": "listed"},
    {"call": "3SB", "site": "Datong, China", "freqs": (20600, 10600), "lat": 39.942959, "lon": 113.247886, "status": "listed"},
    {"call": "3SA", "site": "Changde, China", "freqs": (20600,), "lat": 29.589879, "lon": 110.738701, "status": "listed"},
    {"call": "REN", "site": "Guardamar del Segura, Spain", "freqs": (145000,), "lat": 38.071871, "lon": -0.664625, "status": "listed"},
    {"call": "OmegaB_TT", "site": "Chaguaramas, Trinidad", "freqs": (12000,), "lat": 10.699738, "lon": -61.638386, "status": "gone"},
    {"call": "OmegaB_LR", "site": "Paynesville, Liberia", "freqs": (12000,), "lat": 6.305442, "lon": -10.662068, "status": "gone"},
    {"call": "OmegaC", "site": "Haiku Valley, Hawaii, USA", "freqs": (11800,), "lat": 21.404811, "lon": -157.830834, "status": "gone"},
    {"call": "OmegaA", "site": "Brattland, Norway", "freqs": (12100,), "lat": 66.419323, "lon": 13.12995, "status": "gone"},
    {"call": "OmegaE", "site": "Saint-Paul, Reunion", "freqs": (12300,), "lat": -20.974153, "lon": 55.289973, "status": "gone"},
    {"call": "OmegaF", "site": "Golfo Nuevo, Argentina", "freqs": (12900,), "lat": -43.053524, "lon": -65.190763, "status": "gone"},
    {"call": "OmegaG", "site": "Woodside, Victoria, Australia", "freqs": (13000, 18600), "lat": -38.481268, "lon": 146.935326, "status": "gone"},
    {"call": "OmegaH", "site": "Tsushima Island, Japan", "freqs": (12800,), "lat": 34.614763, "lon": 129.45383, "status": "gone"},
    {"call": "GBZ", "site": "Criggion, Wales, UK", "freqs": (15200,), "lat": 52.72246, "lon": -3.06295, "status": "gone"},
    {"call": "Kahuku", "site": "Kahuku, Oahu, Hawaii, USA", "freqs": (16100,), "lat": 21.7062, "lon": -157.9731, "status": "gone"},
    {"call": "Coltano", "site": "Coltano, Italy", "freqs": (), "lat": 43.649841, "lon": 10.408634, "status": "gone"},
    {"call": "Waunfawr", "site": "Waunfawr, Wales, UK", "freqs": (21200,), "lat": 53.1239, "lon": -4.1935, "status": "gone"},
    {"call": "Kootwijk", "site": "Apeldoorn, Netherlands", "freqs": (24000,), "lat": 52.173414, "lon": 5.818857, "status": "gone"},
    {"call": "TableHead", "site": "Glace Bay, Nova Scotia, Canada", "freqs": (37500,), "lat": 46.21118, "lon": -59.9525, "status": "gone"},
    {"call": "MarconiTowers", "site": "Glace Bay, Nova Scotia, Canada", "freqs": (37500,), "lat": 46.1547273, "lon": -59.9455246, "status": "gone"},
    {"call": "Marion", "site": "Marion, Massachusetts, USA", "freqs": (25800,), "lat": 41.7131401, "lon": -70.7748406, "status": "gone"},
    {"call": "NewBrunswick", "site": "New Brunswick, New Jersey, USA", "freqs": (21800,), "lat": 40.51529, "lon": -74.48895, "status": "gone"},
    {"call": "Bolinas", "site": "Bolinas, California, USA", "freqs": (19200,), "lat": 37.913, "lon": -122.72825, "status": "gone"},
    {"call": "RadioCentral", "site": "Rocky Point, New York, USA", "freqs": (18300,), "lat": 40.92379, "lon": -72.9356, "status": "gone"},
    {"call": "NSS", "site": "Annapolis, Maryland, USA", "freqs": (21400,), "lat": 38.977778, "lon": -76.453333, "status": "gone"},
    {"call": "Forestport", "site": "Forestport, New York, USA", "freqs": (), "lat": 43.44485337, "lon": -75.0861464, "status": "gone"},
    {"call": "Tuckerton", "site": "Tuckerton, New Jersey, USA", "freqs": (22100,), "lat": 39.558495, "lon": -74.37057, "status": "gone"},
    {"call": "SilverCreek", "site": "Silver Creek, Nebraska, USA", "freqs": (), "lat": 41.3461996, "lon": -97.72176109, "status": "gone"},
    {"call": "Hawes", "site": "Hinkley, California, USA", "freqs": (), "lat": 34.9174009, "lon": -117.377046654, "status": "gone"},
    {"call": "GBR", "site": "Rugby, UK", "freqs": (16000, 60000), "lat": 52.36729, "lon": -1.188524, "status": "gone"},
    {"call": "JAP", "site": "Yosami, Kariya, Japan", "freqs": (17442,), "lat": 34.971474, "lon": 137.017018, "status": "gone"},
    {"call": "NBA", "site": "Summit, Balboa, Panama", "freqs": (18600, 24000), "lat": 9.0699425, "lon": -79.6333477, "status": "gone"},
    {"call": "NPO", "site": "Cavite, Philippines", "freqs": (21500,), "lat": 14.495, "lon": 120.908, "status": "gone"},
    {"call": "Malabar", "site": "Malabar, Indonesia", "freqs": (), "lat": -7.116281, "lon": 107.606183, "status": "gone"},
    {"call": "NPM_old", "site": "Pearl Harbor, Hawaii, USA", "freqs": (26100,), "lat": 21.35, "lon": -157.964, "status": "gone"},
    {"call": "NPL", "site": "San Diego, California, USA", "freqs": (30600,), "lat": 32.74063, "lon": -117.0643, "status": "gone"},
    {"call": "Sayville", "site": "Sayville, New York, USA", "freqs": (38400,), "lat": 40.7437, "lon": -73.1033, "status": "gone"},
    {"call": "Karlsborg", "site": "Karlsborg, Sweden", "freqs": (49550,), "lat": 58.4870111, "lon": 14.4691833, "status": "gone"},
    {"call": "NAA_old", "site": "Arlington, Virginia, USA", "freqs": (50000,), "lat": 38.86782, "lon": -77.0791, "status": "gone"},
    {"call": "OMA", "site": "Liblice, Czechia", "freqs": (50000,), "lat": 50.072249, "lon": 14.88081, "status": "gone"},
    {"call": "OLB5", "site": "Podebrady, Czechia", "freqs": (50000,), "lat": 50.137793, "lon": 15.144331, "status": "gone"},
    {"call": "FTA50", "site": "Saint-Andre-de-Corcy, France", "freqs": (50750,), "lat": 45.928825, "lon": 4.935737, "status": "gone"},
    {"call": "Hurup", "site": "Hurup, Germany", "freqs": (53000, 68900), "lat": 54.760504, "lon": 9.549544, "status": "gone"},
    {"call": "Neuharlingersiel", "site": "Neuharlingersiel, Germany", "freqs": (53000,), "lat": 53.677881, "lon": 7.612077, "status": "gone"},
    {"call": "Clifden", "site": "Derrigimlagh, Clifden, Ireland", "freqs": (54500,), "lat": 53.4508506, "lon": -10.0430238, "status": "gone"},
    {"call": "BadDeutsch", "site": "Bad Deutsch-Altenburg, Austria", "freqs": (73850,), "lat": 48.106176, "lon": 16.920359, "status": "gone"},
    {"call": "HBG", "site": "Prangins, Switzerland", "freqs": (75000,), "lat": 46.408422, "lon": 6.25268, "status": "gone"},
    {"call": "Szekesfehervar", "site": "Szekesfehervar, Hungary", "freqs": (77820,), "lat": 47.152844, "lon": 18.395201, "status": "gone"},
    {"call": "Munchenbuchsee", "site": "Munchenbuchsee, Switzerland", "freqs": (82050,), "lat": 47.014617, "lon": 7.443483, "status": "gone"},
    {"call": "Dubendorf", "site": "Dubendorf, Switzerland", "freqs": (), "lat": 47.40882, "lon": 8.631778, "status": "gone"},
    {"call": "XPH", "site": "Thule, Greenland", "freqs": (68900,), "lat": 76.553133, "lon": -68.5507134, "status": "gone"},
    {"call": "SOA", "site": "Radom-Wacyn, Poland", "freqs": (55750, 58250, 62450, 64900, 76350, 80500, 81350), "lat": 51.409332, "lon": 21.117214, "status": "gone"},
    {"call": "AXO", "site": "Babice, Warsaw, Poland", "freqs": (14290, 16400, 17700, 18650), "lat": 52.266412, "lon": 20.879892, "status": "gone"},
    {"call": "Eilvese", "site": "Eilvese, Germany", "freqs": (20000, 30000, 96000), "lat": 52.546389, "lon": 9.414722, "status": "gone"},
    {"call": "KoenigsWh", "site": "Koenigs Wusterhausen, Germany", "freqs": (69700,), "lat": 52.304277, "lon": 13.611326, "status": "gone"},
    {"call": "Kamina", "site": "Kamina, Atakpame, Togo", "freqs": (), "lat": 7.933333, "lon": 0.85, "status": "gone"},
    {"call": "Herzogstand", "site": "Herzogstand, Germany", "freqs": (), "lat": 47.628889, "lon": 11.322222, "status": "gone"},
    {"call": "Goliath", "site": "Kalbe, Germany", "freqs": (16550,), "lat": 52.669218, "lon": 11.42189, "status": "gone"},
    {"call": "Nauen", "site": "Nauen, Germany", "freqs": (), "lat": 52.647959, "lon": 12.908292, "status": "gone"},
    {"call": "SRC_Ruda", "site": "Ruda, Sweden", "freqs": (44200, 40000), "lat": 57.120331, "lon": 16.153111, "status": "gone"},
    {"call": "Lafayette", "site": "Marcheprime, France", "freqs": (), "lat": 44.708611, "lon": -0.813611, "status": "gone"},
    {"call": "BasseLande", "site": "Brains, France", "freqs": (), "lat": 47.170749, "lon": -1.694947, "status": "gone"},
)

COLUMNS = (
    ("call", "station", 14, "<"),
    ("freq_khz", "khz", 7, ">"),
    ("lat", "lat", 10, ">"),
    ("lon", "lon", 11, ">"),
    ("bearing_deg", "brg", 6, ">"),
    ("bearing_plus", "+90", 6, ">"),
    ("bearing_minus", "-90", 6, ">"),
    ("solar_noon_utc", "noon utc", 9, ">"),
    ("sun_elev_deg", "elev", 6, ">"),
    ("distance_km", "km", 9, ">"),
)


def clear_screen():
    os.system("clear" if os.name == "posix" else "cls")


def solar_noon(year, month, day, lat, lon, tz_offset=0.0):
    """upper transit in minutes after local midnight, plus max sun elevation."""
    # noaa fourier fit, good to about half a minute and needs no ephemeris
    doy = datetime(year, month, day).timetuple().tm_yday
    gamma = 2.0 * math.pi * (doy - 1) / 365.0
    eqtime = 229.18 * (
        0.000075
        + 0.001868 * math.cos(gamma)
        - 0.032077 * math.sin(gamma)
        - 0.014615 * math.cos(2 * gamma)
        - 0.040849 * math.sin(2 * gamma)
    )
    # earth turns 1 degree per 4 minutes, so longitude just shifts the 720 min base
    minutes = (720.0 - 4.0 * lon - eqtime + tz_offset * 60.0) % 1440.0
    decl = math.degrees(
        0.006918
        - 0.399912 * math.cos(gamma)
        + 0.070257 * math.sin(gamma)
        - 0.006758 * math.cos(2 * gamma)
        + 0.000907 * math.sin(2 * gamma)
        - 0.002697 * math.cos(3 * gamma)
        + 0.001480 * math.sin(3 * gamma)
    )
    return minutes, 90.0 - abs(lat - decl)


def hhmmss(minutes):
    # seconds carry handled by the modulo, no manual 59->60 patching
    secs = int(round(minutes * 60.0)) % 86400
    return "%02d:%02d:%02d" % (secs // 3600, secs // 60 % 60, secs % 60)


def bearing(obs_lat, obs_lon, tx_lat, tx_lon):
    """initial great circle bearing from observer to transmitter, 0 to 360."""
    # same identity the qibla formula uses, numerator and denominator over cos(tx_lat)
    dlon = math.radians(tx_lon - obs_lon)
    y = math.sin(dlon)
    x = math.cos(math.radians(obs_lat)) * math.tan(math.radians(tx_lat)) - math.sin(
        math.radians(obs_lat)
    ) * math.cos(dlon)
    return math.degrees(math.atan2(y, x)) % 360.0


def great_circle_km(obs_lat, obs_lon, tx_lat, tx_lon, radius=R_EARTH_KM):
    """spherical law of cosines distance in km."""
    cos_d = math.sin(math.radians(obs_lat)) * math.sin(math.radians(tx_lat)) + math.cos(
        math.radians(obs_lat)
    ) * math.cos(math.radians(tx_lat)) * math.cos(math.radians(tx_lon - obs_lon))
    # clamp or acos blows up on 1.0000000000000002 when you sit on a station
    return radius * math.acos(max(-1.0, min(1.0, cos_d)))


def locate_by_ip():
    # geocoder for auto detecting lat/long
    try:
        import geocoder
    except ImportError:
        print("geocoder missing, install with: pip install geocoder")
        return None
    try:
        fix = geocoder.ip("me").latlng
    except Exception as err:
        print("ip lookup failed: %s" % err)
        return None
    if not fix:
        print("ip lookup returned nothing")
        return None
    return float(fix[0]), float(fix[1])


def ask_manual():
    # typed fallback when the ip fix is wrong or offline
    while True:
        try:
            lat = float(input("lat: ").strip())
            lon = float(input("lon: ").strip())
        except (EOFError, KeyboardInterrupt):
            sys.exit("\nno location, nothing to compute")
        except ValueError:
            print("numbers only")
            continue
        if -90.0 <= lat <= 90.0 and -180.0 <= lon <= 180.0:
            return lat, lon
        print("lat -90..90, lon -180..180")


def confirm_location(fix):
    # ask the user if its correct before anything is computed
    if fix is None:
        print("no automatic fix, type it in")
        return ask_manual()
    lat, lon = fix
    print("detected %.5f, %.5f" % (lat, lon))
    if not sys.stdin.isatty():
        print("not a terminal, keeping it")
        return lat, lon
    while True:
        try:
            answer = input("correct? [y/n] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            sys.exit("\nnothing confirmed, stopping")
        if answer in ("", "y", "yes"):
            return lat, lon
        if answer in ("n", "no"):
            return ask_manual()


def resolve_location(lat=None, lon=None):
    """forced geocoder path unless both coords are passed in."""
    if lat is not None and lon is not None:
        return float(lat), float(lon)
    return confirm_location(locate_by_ip())


def build_rows(obs_lat, obs_lon, day=None, include_gone=False, tz_offset=0.0):
    """one dict per transmitter, sorted near to far, ready to index or filter."""
    day = day or date.today()
    rows = []
    for st in STATIONS:
        if st["status"] == "gone" and not include_gone:
            continue
        minutes, elev = solar_noon(day.year, day.month, day.day, st["lat"], st["lon"], tz_offset)
        brg = bearing(obs_lat, obs_lon, st["lat"], st["lon"])
        rows.append(
            {
                "call": st["call"],
                "site": st["site"],
                "status": st["status"],
                "freq_hz": st["freqs"][0] if st["freqs"] else None,
                "freqs_hz": list(st["freqs"]),
                "freq_khz": round(st["freqs"][0] / 1000.0, 3) if st["freqs"] else None,
                "lat": st["lat"],
                "lon": st["lon"],
                "bearing_deg": round(brg, 1),
                "bearing_plus": round((brg + 90.0) % 360.0, 1),
                "bearing_minus": round((brg - 90.0) % 360.0, 1),
                "solar_noon_utc": hhmmss(minutes),
                "sun_elev_deg": round(elev, 1),
                "distance_km": round(great_circle_km(obs_lat, obs_lon, st["lat"], st["lon"]), 1),
                "note": st.get("note", ""),
            }
        )
    rows.sort(key=lambda r: r["distance_km"])
    return rows


def pick(rows, call):
    # pick(rows, "naa")["bearing_deg"] and similar one liners
    key = call.strip().lower()
    for row in rows:
        if row["call"].lower() == key:
            return row
    return None


def near(rows, limit_km):
    return [row for row in rows if row["distance_km"] <= limit_km]


def cell(rows):
    """table as header list plus row lists, the shape print and pdf both consume."""
    header = [label for _, label, _, _ in COLUMNS]
    body = []
    for row in rows:
        body.append([("" if row[key] is None else str(row[key])) for key, _, _, _ in COLUMNS])
    return header, body


def print_table(rows):
    header, body = cell(rows)
    widths = [w for _, _, w, _ in COLUMNS]
    aligns = [a for _, _, _, a in COLUMNS]
    print(" ".join("%*s" % (w, h) if a == ">" else "%-*s" % (w, h) for h, w, a in zip(header, widths, aligns)))
    for line in body:
        print(" ".join("%*s" % (w, v) if a == ">" else "%-*s" % (w, v[:w]) for v, w, a in zip(line, widths, aligns)))


def write_json(rows, path, meta):
    with open(path, "w", encoding="ascii") as handle:
        json.dump({"observer": meta, "stations": rows}, handle, indent=2)
    return path


def write_csv(rows, path):
    fields = list(rows[0].keys()) if rows else []
    with open(path, "w", newline="", encoding="ascii") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            out = dict(row)
            out["freqs_hz"] = " ".join(str(f) for f in row["freqs_hz"])
            writer.writerow(out)
    return path


def write_pdf(rows, path, meta):
    """same cell, on paper"""
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    header, body = cell(rows)
    title = "vlf transmitters from %.4f, %.4f on %s" % (meta["lat"], meta["lon"], meta["date"])
    styles = getSampleStyleSheet()

    def stamp(canvas, _doc):
        # keep the file metadata plain instead of whatever the toolchain writes
        canvas.setTitle(title)
        canvas.setAuthor(meta.get("author", ""))
        canvas.setSubject("vlf bearings, distances and solar noon")
        canvas.setCreator("vlf_transit.py")
        canvas.setProducer("")

    doc = SimpleDocTemplate(
        path,
        pagesize=landscape(A4),
        leftMargin=12 * mm,
        rightMargin=12 * mm,
        topMargin=12 * mm,
        bottomMargin=12 * mm,
        title=title,
        author=meta.get("author", ""),
    )
    table = Table([header] + body, repeatRows=1)
    table.setStyle(
        TableStyle(
            [
                ("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 7),
                ("FONT", (0, 1), (-1, -1), "Helvetica", 7),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.lightgrey),
                ("BACKGROUND", (0, 0), (-1, 0), colors.whitesmoke),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.Color(0.97, 0.97, 0.97)]),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
            ]
        )
    )
    doc.build([Paragraph(title, styles["Heading4"]), Spacer(1, 4), table], onFirstPage=stamp, onLaterPages=stamp)
    return path


def parse_args(argv=None):
    ap = argparse.ArgumentParser(description="vlf transmitter bearings, distances and solar noon")
    ap.add_argument("--lat", type=float, help="skip the ip lookup")
    ap.add_argument("--lon", type=float, help="skip the ip lookup")
    ap.add_argument("--date", help="yyyy-mm-dd, default today")
    ap.add_argument("--all", action="store_true", help="include demolished sites")
    ap.add_argument("--out", default=".", help="folder for the exports")
    ap.add_argument("--no-files", action="store_true", help="print only")
    return ap.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    clear_screen()
    day = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else date.today()
    lat, lon = resolve_location(args.lat, args.lon)
    rows = build_rows(lat, lon, day=day, include_gone=args.all)
    meta = {"lat": lat, "lon": lon, "date": day.isoformat(), "count": len(rows)}
    my_noon, my_elev = solar_noon(day.year, day.month, day.day, lat, lon)
    print("observer %.5f %.5f  noon %s utc  sun %.1f deg  %d stations" % (lat, lon, hhmmss(my_noon), my_elev, len(rows)))
    print_table(rows)
    if args.no_files:
        return rows
    os.makedirs(args.out, exist_ok=True)
    made = [
        write_json(rows, os.path.join(args.out, "vlf_table.json"), meta),
        write_csv(rows, os.path.join(args.out, "vlf_table.csv")),
        write_pdf(rows, os.path.join(args.out, "vlf_table.pdf"), meta),
    ]
    print("wrote " + ", ".join(os.path.basename(p) for p in made))
    return rows


if __name__ == "__main__":
    main()
