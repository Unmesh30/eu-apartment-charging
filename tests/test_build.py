import json
import re
from datetime import datetime, timezone

import pytest

from pipeline import build
from pipeline.countries import CODES

NOW = datetime(2026, 11, 21, 23, 40, tzinfo=timezone.utc)


def test_estimates_are_cars_times_shares(world):
    data = build.collect(world.fetch, NOW)
    fr, de = data["rows"]["FR"], data["rows"]["DE"]
    assert fr["est_big"] == round(1_543_440 * 25.8 / 100) == 398_208
    assert fr["est_all"] == round(1_543_440 * 36.7 / 100)
    assert de["est_all"] == round(2_034_260 * 58.6 / 100) == 1_192_076
    assert de["growth"] == round(100 * (2_034_260 / 1_651_643 - 1), 3)
    assert data["rows"]["AT"]["growth"] == pytest.approx(28.471, abs=0.001)  # shown as +28%, not +29%
    assert fr["flags"] == "i"


def test_the_three_takeaways_follow_the_numbers(world):
    takeaways = build.collect(world.fetch, NOW)["insights"]
    assert takeaways[0] == ("Germany has the most electric cars in flats (1.19M), but in buildings with 10+ flats "
                            "France leads (398k vs 352k).")
    assert takeaways[1].startswith("In Germany, 7 in 10 people who live in a flat")
    assert takeaways[2].startswith("Spain has the highest share of people in big apartment buildings of the top ten (45.9%)")


def test_when_one_country_leads_both_ways_the_takeaway_says_so(world):
    from tests.conftest import set_cell
    set_cell(world.cars, 1_000_000, mot_nrg="ELC", geo="FR", time="2025")
    takeaways = build.collect(world.fetch, NOW)["insights"]
    assert takeaways[0].startswith("Germany leads on both measures")


def test_all_checks_pass_on_the_real_data(world):
    data = build.collect(world.fetch, NOW)
    assert data["warnings"] == []
    assert len(data["checks"]) == 9
    assert all(check["ok"] for check in data["checks"])


def test_a_failed_source_keeps_its_last_good_data_and_says_so(world):
    previous = build.collect(world.fetch, NOW)
    world.fail.add("homes")
    data = build.collect(world.fetch, NOW, previous)
    assert data["sources"]["homes"]["fresh"] is False
    assert data["sources"]["cars"]["fresh"] is True
    assert len(data["warnings"]) == 1 and "homes-survey" in data["warnings"][0]
    assert data["rows"]["FR"]["est_big"] == 398_208


def test_with_no_last_good_data_a_failure_stops_the_build(world):
    world.fail.add("cars")
    with pytest.raises(RuntimeError):
        build.collect(world.fetch, NOW)


def test_the_page_and_the_slide_are_filled_in(world, tmp_path):
    data = build.collect(world.fetch, NOW)
    build.write_site(data, tmp_path)
    page = (tmp_path / "index.html").read_text(encoding="utf-8")
    slide = (tmp_path / "slide.html").read_text(encoding="utf-8")
    assert "__DATA__" not in page
    assert not re.search(r"__[A-Z_]+__", slide)
    embedded = json.loads(page.split("const DATA = ", 1)[1].split(";\n", 1)[0])
    assert set(embedded["rows"]) == set(CODES)
    assert "France (imputed)" in slide  # no flag is hidden on the slide
    assert slide.count('class="big"') == build.TOP


def test_people_formats_like_the_page():
    assert build.people(2_034_260) == "2.03M"
    assert build.people(1_192_076) == "1.19M"
    assert build.people(1_500_000) == "1.5M"
    assert build.people(398_208) == "398k"
    assert build.people(493) == "493"
