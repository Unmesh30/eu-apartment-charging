"""Eurostat: electric cars on the road, and how many people live in flats, in each EU country.

Both come from Eurostat's public dissemination API, which answers in JSON-stat 2.0:
  road_eqs_carpda  passenger cars by motor energy (count at the end of each year)
  ilc_lvho01       share of people by type of home (EU-SILC survey)
"""
import json
from urllib.parse import urlencode

from .countries import CODES
from .errors import DataError

API = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data/"
TABLE_PAGE = "https://ec.europa.eu/eurostat/databrowser/view/{dataset}/default/table?lang=en"

CARS = "road_eqs_carpda"
HOMES = "ilc_lvho01"
HOME_TYPES = ["HOUSE", "FLAT", "FLAT_LT10", "FLAT_GE10", "OTH"]

# Eurostat's observation flags. A number that carries one is shown with it, never without.
FLAG_MEANINGS = {
    "b": "break in series",
    "c": "confidential",
    "d": "definition differs",
    "e": "estimated",
    "f": "forecast",
    "i": "imputed",
    "n": "not significant",
    "p": "provisional",
    "r": "revised",
    "s": "Eurostat estimate",
    "u": "low reliability",
    "z": "not applicable",
}

# Electric cars above this share of all cars would mean a unit or code mix-up, not a real market.
MAX_EV_SHARE = 60.0
# A year-on-year change outside this range is shown as a warning to look at, not hidden.
GROWTH_RANGE = (-10.0, 150.0)
# Shares that should add up, and how far rounding may move them.
SUM_TOLERANCE = 1.5
SPLIT_TOLERANCE = 1.0


def table_url(dataset, **dimensions):
    """Build an API query. A list value asks for several codes of one dimension."""
    params = [("format", "JSON"), ("lang", "EN")]
    for name, value in dimensions.items():
        for item in value if isinstance(value, (list, tuple)) else [value]:
            params.append((name, str(item)))
    return API + dataset + "?" + urlencode(params)


def cars_url():
    return table_url(CARS, unit="NR", mot_nrg=["ELC", "TOTAL"], leg_form="TOTAL", geo=CODES, lastTimePeriod=4)


def homes_url():
    return table_url(HOMES, unit="PC", deg_urb="TOTAL", rskpovth="TOTAL", building=HOME_TYPES, geo=CODES, lastTimePeriod=4)


def load(fetch, url):
    try:
        return json.loads(fetch(url))
    except json.JSONDecodeError as error:
        raise DataError(f"Eurostat sent something that is not JSON ({error})") from None


def decode(doc):
    """Return (dimension ids, {tuple of codes: (value, flag)}) for a JSON-stat 2.0 dataset."""
    if not isinstance(doc, dict) or "id" not in doc or "size" not in doc:
        raise DataError(f"Eurostat answered without a dataset: {str(doc)[:200]}")
    ids, sizes = doc["id"], doc["size"]
    codes_by_dimension = []
    for dimension in ids:
        index = doc["dimension"][dimension]["category"]["index"]
        if isinstance(index, list):
            codes = list(index)
        else:
            codes = [None] * len(index)
            for code, position in index.items():
                codes[position] = code
        codes_by_dimension.append(codes)
    values = doc.get("value") or {}
    if isinstance(values, list):
        values = {str(i): v for i, v in enumerate(values)}
    flags = doc.get("status") or {}
    if isinstance(flags, list):
        flags = {str(i): f for i, f in enumerate(flags) if f}
    cells = {}
    for flat, value in values.items():
        if value is None:
            continue  # a gap stays a gap; it is never read as zero
        rest, coords = int(flat), []
        for size in reversed(sizes):
            coords.append(rest % size)
            rest //= size
        coords.reverse()
        key = tuple(codes_by_dimension[i][c] for i, c in enumerate(coords))
        cells[key] = (float(value), flags.get(flat, ""))
    return ids, cells


def _keyed(doc, varying):
    """{(geo, year, <varying code>): (value, flag)}, after checking every other dimension has one code."""
    ids, cells = decode(doc)
    for dimension, size in zip(ids, doc["size"]):
        if dimension not in ("geo", "time", varying) and size != 1:
            raise DataError(f"Eurostat returned {size} codes for '{dimension}' where one was asked for")
    g, t, v = ids.index("geo"), ids.index("time"), ids.index(varying)
    return {(key[g], int(key[t]), key[v]): cell for key, cell in cells.items()}


def _full_years(table, kinds, countries=CODES):
    """Years in which every country has a number of every kind."""
    years = {year for (_, year, _) in table}
    return sorted(y for y in years if all((c, y, k) in table for c in countries for k in kinds))


def _places(codes):
    return ", ".join(codes)


def pull_cars(fetch):
    """Electric and all passenger cars per country, for the latest full year and the one before."""
    doc = load(fetch, cars_url())
    table = _keyed(doc, "mot_nrg")
    years = _full_years(table, ["ELC", "TOTAL"])
    if not years:
        raise DataError("no year has electric-car counts for all 27 countries")
    year = years[-1]
    prev = year - 1
    if prev not in years:
        raise DataError(f"electric-car counts for {prev} are missing for some countries, so growth can't be worked out")

    ev = {c: table[(c, year, "ELC")][0] for c in CODES}
    ev_prev = {c: table[(c, prev, "ELC")][0] for c in CODES}
    cars = {c: table[(c, year, "TOTAL")][0] for c in CODES}
    flags = {c: table[(c, year, "ELC")][1] for c in CODES if table[(c, year, "ELC")][1]}

    for c in CODES:
        if ev[c] < 0 or ev_prev[c] < 0 or cars[c] <= 0:
            raise DataError(f"{c}: a car count is negative or zero")
        if ev[c] > cars[c] * MAX_EV_SHARE / 100:
            raise DataError(f"{c}: electric cars are {100 * ev[c] / cars[c]:.0f}% of all cars, which points to a mix-up")
    growth = {c: (100 * (ev[c] / ev_prev[c] - 1) if ev_prev[c] else None) for c in CODES}
    outliers = [c for c in CODES if growth[c] is None or not GROWTH_RANGE[0] <= growth[c] <= GROWTH_RANGE[1]]

    checks = [
        {"ok": True, "text": f"Electric cars: all 27 countries, {prev} and {year}"},
        {"ok": True, "text": f"Electric cars under {MAX_EV_SHARE:.0f}% of all cars (unit check)"},
        {
            "ok": not outliers,
            "text": (f"Yearly change within {GROWTH_RANGE[0]:+.0f}% to {GROWTH_RANGE[1]:+.0f}% everywhere"
                     if not outliers else f"Unusual yearly change to look at: {_places(outliers)}"),
            "detail": "A jump outside this range is usually a change in how a country counts, not a real market move.",
        },
    ]
    return {
        "dataset": CARS,
        "year": year,
        "prev_year": prev,
        "ev": {c: int(round(ev[c])) for c in CODES},
        "ev_prev": {c: int(round(ev_prev[c])) for c in CODES},
        "cars": {c: int(round(cars[c])) for c in CODES},
        "flags": flags,
        "updated": doc.get("updated", ""),
        "table_page": TABLE_PAGE.format(dataset=CARS),
        "checks": checks,
    }


def pull_homes(fetch):
    """Share of people living in a house, a flat, a small block (<10 flats) or a big block (10+ flats)."""
    doc = load(fetch, homes_url())
    table = _keyed(doc, "building")
    years = _full_years(table, ["HOUSE", "FLAT", "FLAT_LT10", "FLAT_GE10"])
    if not years:
        raise DataError("no survey year covers all 27 countries")
    year = years[-1]

    def share(c, kind):
        cell = table.get((c, year, kind))
        return cell[0] if cell else None

    shares = {kind: {c: share(c, kind) for c in CODES} for kind in HOME_TYPES}
    for kind, values in shares.items():
        for c, v in values.items():
            if v is not None and not 0 <= v <= 100:
                raise DataError(f"{c}: share of people in '{kind}' is {v}, outside 0-100")
    for c in CODES:
        total = shares["HOUSE"][c] + shares["FLAT"][c] + (shares["OTH"][c] or 0)
        if abs(total - 100) > SUM_TOLERANCE:
            raise DataError(f"{c}: houses, flats and other homes add up to {total:.1f}%, not 100%")
        split = shares["FLAT_LT10"][c] + shares["FLAT_GE10"][c]
        if abs(split - shares["FLAT"][c]) > SPLIT_TOLERANCE:
            raise DataError(f"{c}: small and big blocks add up to {split:.1f}%, but flats are {shares['FLAT'][c]:.1f}%")

    flags = {}
    for c in CODES:
        found = set()
        for kind in ("FLAT", "FLAT_GE10"):
            found.update(table[(c, year, kind)][1])
        if found:
            flags[c] = "".join(sorted(found))

    checks = [
        {"ok": True, "text": f"Homes survey: all 27 countries, {year}"},
        {"ok": True, "text": f"Houses + flats + other = 100% (±{SUM_TOLERANCE}) everywhere"},
        {"ok": True, "text": f"Small + big blocks = all flats (±{SPLIT_TOLERANCE}) everywhere"},
    ]
    return {
        "dataset": HOMES,
        "year": year,
        "flat": shares["FLAT"],
        "big": shares["FLAT_GE10"],
        "small": shares["FLAT_LT10"],
        "house": shares["HOUSE"],
        "flags": flags,
        "updated": doc.get("updated", ""),
        "table_page": TABLE_PAGE.format(dataset=HOMES),
        "checks": checks,
    }
