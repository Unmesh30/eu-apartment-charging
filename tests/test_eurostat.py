import pytest

from pipeline import eurostat
from pipeline.countries import CODES
from pipeline.errors import DataError
from tests.conftest import set_cell


def test_cars_from_the_saved_answer(world):
    cars = eurostat.pull_cars(world.fetch)
    assert (cars["year"], cars["prev_year"]) == (2025, 2024)
    assert cars["ev"]["DE"] == 2_034_260
    assert cars["ev"]["FR"] == 1_543_440
    assert cars["ev_prev"]["ES"] == 208_240
    assert cars["cars"]["DE"] == 49_486_487
    assert cars["flags"]["FR"] == "i"  # France's 2025 count is imputed, and the page must say so
    assert cars["flags"]["PT"] == "p"
    assert set(cars["ev"]) == set(CODES)
    assert all(check["ok"] for check in cars["checks"])


def test_homes_from_the_saved_answer(world):
    homes = eurostat.pull_homes(world.fetch)
    assert homes["year"] == 2025
    assert (homes["flat"]["DE"], homes["big"]["DE"], homes["small"]["DE"]) == (58.6, 17.3, 41.3)
    assert (homes["flat"]["FR"], homes["big"]["FR"]) == (36.7, 25.8)
    assert homes["flags"]["LT"] == "p"
    assert homes["flags"]["LU"] == "b"
    assert all(check["ok"] for check in homes["checks"])


def test_a_unit_mix_up_is_refused(world):
    # Electric cars suddenly above 60% of all cars: a code or unit mix-up, not a market.
    set_cell(world.cars, 40_000_000, mot_nrg="ELC", geo="DE", time="2025")
    with pytest.raises(DataError, match="mix-up"):
        eurostat.pull_cars(world.fetch)


def test_a_missing_country_falls_back_to_the_last_full_year(world):
    set_cell(world.cars, None, mot_nrg="ELC", geo="MT", time="2025")
    cars = eurostat.pull_cars(world.fetch)
    assert (cars["year"], cars["prev_year"]) == (2024, 2023)


def test_without_the_year_before_there_is_no_growth_so_it_stops(world):
    for year in ("2022", "2023", "2024"):
        set_cell(world.cars, None, mot_nrg="ELC", geo="CY", time=year)
    with pytest.raises(DataError, match="growth"):
        eurostat.pull_cars(world.fetch)


def test_an_odd_jump_is_shown_not_hidden(world):
    set_cell(world.cars, 60_000, mot_nrg="ELC", geo="EE", time="2025")  # about six times 2024
    cars = eurostat.pull_cars(world.fetch)
    jump = [c for c in cars["checks"] if not c["ok"]]
    assert len(jump) == 1 and "EE" in jump[0]["text"]


def test_shares_that_do_not_add_up_are_refused(world):
    set_cell(world.homes, 70.0, building="FLAT", geo="IT", time="2025")
    with pytest.raises(DataError):
        eurostat.pull_homes(world.fetch)


def test_a_split_that_does_not_match_is_refused(world):
    set_cell(world.homes, 30.0, building="FLAT_GE10", geo="IT", time="2025")
    with pytest.raises(DataError, match="blocks"):
        eurostat.pull_homes(world.fetch)


def test_a_share_out_of_range_is_refused(world):
    set_cell(world.homes, 120.0, building="HOUSE", geo="SE", time="2025")
    with pytest.raises(DataError, match="outside 0-100"):
        eurostat.pull_homes(world.fetch)


def test_something_that_is_not_json_is_refused():
    with pytest.raises(DataError, match="not JSON"):
        eurostat.pull_cars(lambda url, **_: b"<html>maintenance</html>")


def test_an_answer_without_a_dataset_is_refused():
    with pytest.raises(DataError, match="without a dataset"):
        eurostat.pull_homes(lambda url, **_: b'{"error": "busy"}')


def test_queries_ask_for_all_27_countries():
    for url in (eurostat.cars_url(), eurostat.homes_url()):
        assert all(f"geo={code}" in url for code in CODES)
