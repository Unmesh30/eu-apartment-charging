"""Pull both Eurostat tables, check them, and build the page and the investor slide.

    python -m pipeline.build --data data/latest.json --out site

If a source fails a check, the page keeps that source's last good data and says so on screen.
"""
import argparse
import html
import json
import os
import shutil
from datetime import datetime, timezone
from pathlib import Path

from . import eurostat
from .countries import CODES, EU27
from .http import fetch as http_fetch
from .rules import GERMANY_2027

ROOT = Path(__file__).resolve().parent.parent
SITE_SOURCE = ROOT / "site_src"

SOURCE_LABELS = {"cars": "electric-car", "homes": "homes-survey"}

AUTHOR = {
    "name": "Unmesh Achar",
    "linkedin": "https://www.linkedin.com/in/unmesh-achar-319467210/",
    "code": "https://github.com/Unmesh30/eu-apartment-charging",
}

TOP = 10  # countries on the slide


def collect(fetch, now, previous=None):
    """Pull and check each source. A source that fails keeps its last good data and adds a warning."""
    stamp = now.strftime("%Y-%m-%dT%H:%MZ")
    pulls = {"cars": lambda: eurostat.pull_cars(fetch), "homes": lambda: eurostat.pull_homes(fetch)}
    sources, warnings = {}, []
    for name, pull in pulls.items():
        try:
            block = pull()
            block["pulled_at"] = stamp
            block["fresh"] = True
        except Exception as error:  # keep this source's last good data, and say so
            old = ((previous or {}).get("sources") or {}).get(name)
            if not old:
                raise
            block = {**old, "fresh": False}
            warnings.append(
                f"Today's {SOURCE_LABELS[name]} update failed ({error}). "
                f"Showing the last good {SOURCE_LABELS[name]} data, pulled {old['pulled_at']}."
            )
        sources[name] = block
    rows = estimates(sources["cars"], sources["homes"])
    return {
        "generated_at": stamp,
        "warnings": warnings,
        "countries": EU27,
        "flag_meanings": eurostat.FLAG_MEANINGS,
        "author": AUTHOR,
        "rules": GERMANY_2027,
        "sources": sources,
        "rows": rows,
        "checks": cross_checks(sources, rows),
        "insights": insights(rows, sources),
    }


def estimates(cars, homes):
    """Per country: electric cars, growth, and the estimate of electric cars in flats."""
    rows = {}
    for c in CODES:
        ev, prev, total = cars["ev"][c], cars["ev_prev"][c], cars["cars"][c]
        flat, big, small = homes["flat"][c], homes["big"][c], homes["small"][c]
        rows[c] = {
            "ev": ev,
            "growth": round(100 * (ev / prev - 1), 3) if prev else None,
            "ev_share": round(100 * ev / total, 3),
            "flat": flat,
            "big": big,
            "small": small,
            "est_all": round(ev * flat / 100),
            "est_big": round(ev * big / 100),
            "flags": "".join(sorted(set(cars["flags"].get(c, "") + homes["flags"].get(c, "")))),
        }
    return rows


def cross_checks(sources, rows):
    cars, homes = sources["cars"], sources["homes"]
    same_year = cars["year"] == homes["year"]
    flagged = sorted(c for c in CODES if rows[c]["flags"])
    names = ", ".join(EU27[c] for c in flagged)
    return [
        *cars["checks"],
        *homes["checks"],
        {
            "ok": same_year,
            "text": (f"Cars and homes from the same year ({cars['year']})" if same_year else
                     f"Cars are from {cars['year']} and homes from {homes['year']}: read the estimate with care"),
        },
        {
            "ok": all(r["est_big"] <= r["est_all"] <= r["ev"] for r in rows.values()),
            "text": "Estimates in order: 10+ flats ≤ all flats ≤ all cars",
        },
        {
            "ok": True,
            "text": f"Eurostat flags shown next to the numbers ({len(flagged)} countries)" if flagged else "No Eurostat flags on these numbers",
            "detail": names,
        },
    ]


def people(n):
    if n >= 1e6:
        return f"{n / 1e6:.2f}".rstrip("0").rstrip(".") + "M"
    if n >= 1e3:
        return f"{n / 1e3:.0f}k"
    return f"{n:.0f}"


def insights(rows, sources):
    """Three takeaways, worked out from the numbers so they stay true when the data changes."""
    name = EU27.__getitem__
    year = sources["cars"]["year"]
    by_all = sorted(CODES, key=lambda c: -rows[c]["est_all"])
    by_big = sorted(CODES, key=lambda c: -rows[c]["est_big"])
    lead_all, lead_big = by_all[0], by_big[0]
    out = []
    if lead_all != lead_big:
        out.append(
            f"{name(lead_all)} has the most electric cars in flats ({people(rows[lead_all]['est_all'])}), "
            f"but in buildings with 10+ flats {name(lead_big)} leads "
            f"({people(rows[lead_big]['est_big'])} vs {people(rows[lead_all]['est_big'])})."
        )
    else:
        out.append(
            f"{name(lead_all)} leads on both measures: {people(rows[lead_all]['est_all'])} electric cars in flats, "
            f"{people(rows[lead_all]['est_big'])} in buildings with 10+ flats."
        )
    de = rows["DE"]
    if de["flat"]:
        tenths = round(10 * de["small"] / de["flat"])
        out.append(
            f"In Germany, {tenths} in 10 people who live in a flat live in a building with fewer than 10 flats. "
            "The 2027 rules apply from 4 parking spaces, so smaller buildings are in scope when built or renovated."
        )
    top = by_big[:TOP]
    roomy = max(top, key=lambda c: rows[c]["big"])
    r = rows[roomy]
    base = f" from a low base ({r['ev_share']:.1f}% of all cars)" if r["ev_share"] < 3 else ""
    out.append(
        f"{name(roomy)} has the highest share of people in big apartment buildings of the top ten ({r['big']:.1f}%), "
        f"and its electric cars grew {r['growth']:.0f}% in {year}{base}."
    )
    return out


def render_page(data):
    page = (SITE_SOURCE / "index.html").read_text(encoding="utf-8")
    if "__DATA__" not in page:
        raise RuntimeError("site_src/index.html is missing its __DATA__ marker")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return page.replace("__DATA__", payload)


def bar_chart(rows, codes, width=700, row_h=42):
    """SVG: for each country, a light bar for all flats with a dark bar for big blocks on top."""
    label_w, value_w = 120, 150
    plot_w = width - label_w - value_w
    top = max(rows[c]["est_all"] for c in codes) or 1
    parts = []
    for i, c in enumerate(codes):
        y = i * row_h
        w_all = plot_w * rows[c]["est_all"] / top
        w_big = plot_w * rows[c]["est_big"] / top
        parts.append(
            f'<text x="{label_w - 12}" y="{y + 26}" text-anchor="end" class="lbl">{html.escape(EU27[c])}</text>'
            f'<rect x="{label_w}" y="{y + 9}" width="{w_all:.1f}" height="24" rx="4" class="all"/>'
            f'<rect x="{label_w}" y="{y + 9}" width="{max(w_big, 2):.1f}" height="24" rx="4" class="big"/>'
            f'<text x="{label_w + max(w_all, 2) + 10:.1f}" y="{y + 26}" class="val">'
            f'<tspan class="vb">{people(rows[c]["est_big"])}</tspan>'
            f'<tspan class="va"> / {people(rows[c]["est_all"])}</tspan></text>'
        )
    height = row_h * len(codes)
    return (f'<svg viewBox="0 0 {width} {height}" width="{width}" height="{height}" role="img" '
            f'aria-label="Estimated electric cars in flats, top {len(codes)} countries">{"".join(parts)}</svg>')


def slide_flags(rows, codes, meanings):
    """One sentence naming the flagged numbers on the slide, so no flag is hidden."""
    marked = [f"{EU27[c]} ({' and '.join(meanings.get(f, f) for f in rows[c]['flags'])})" for c in codes if rows[c]["flags"]]
    return f"Eurostat flags: {', '.join(marked)}. " if marked else ""


def render_slide(data):
    rows, sources, rules = data["rows"], data["sources"], data["rules"]
    year = sources["cars"]["year"]
    codes = sorted(CODES, key=lambda c: -rows[c]["est_big"])[:TOP]
    template = (SITE_SOURCE / "slide.html").read_text(encoding="utf-8")
    takeaways = "".join(f"<li>{html.escape(t)}</li>" for t in data["insights"])
    fills = {
        "__YEAR__": str(year),
        "__HOMES_YEAR__": str(sources["homes"]["year"]),
        "__CHART__": bar_chart(rows, codes),
        "__TAKEAWAYS__": takeaways,
        "__RULE__": html.escape(rules["points"][0]),
        "__RULE_TITLE__": html.escape(rules["title"]),
        "__AUTHOR__": html.escape(data["author"]["name"]),
        "__PULLED__": data["generated_at"][:10],
        "__FLAGS__": slide_flags(rows, codes, data["flag_meanings"]),
    }
    for key, value in fills.items():
        if key not in template:
            raise RuntimeError(f"site_src/slide.html is missing {key}")
        template = template.replace(key, value)
    return template


def main(argv=None):
    parser = argparse.ArgumentParser(description="Pull, check and build the apartment EV charging page.")
    parser.add_argument("--data", default="data/latest.json", help="last good data; updated in place")
    parser.add_argument("--out", default="site", help="folder for the built page")
    args = parser.parse_args(argv)

    data_path = Path(args.data)
    previous = json.loads(data_path.read_text(encoding="utf-8")) if data_path.exists() else None
    data = collect(http_fetch, datetime.now(timezone.utc), previous)

    data_path.parent.mkdir(parents=True, exist_ok=True)
    data_path.write_text(json.dumps(data, ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    write_site(data, Path(args.out))

    for warning in data["warnings"]:
        print(f"::warning::{warning}")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a", encoding="utf-8") as handle:
            handle.write(f"warnings={len(data['warnings'])}\n")
    print(f"Built {args.out} with data pulled {data['generated_at']} ({len(data['warnings'])} warning(s))")


def write_site(data, out):
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(render_page(data), encoding="utf-8")
    (out / "slide.html").write_text(render_slide(data), encoding="utf-8")
    (out / ".nojekyll").write_text("", encoding="utf-8")
    preview = ROOT / "docs" / "preview.png"  # the picture shown when the link is shared
    if preview.exists():
        shutil.copyfile(preview, out / "preview.png")


if __name__ == "__main__":
    main()
