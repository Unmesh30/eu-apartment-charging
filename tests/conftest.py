"""Shared helpers: the real Eurostat answers saved on 21 Nov 2026, and ways to break them on purpose."""
import copy
import json
from pathlib import Path

import pytest

from pipeline import eurostat

FIXTURES = Path(__file__).parent / "fixtures"


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def flat_index(doc, **coords):
    """Position of one cell in a JSON-stat 'value' map, from its codes (e.g. geo='DE', time='2025')."""
    index = 0
    for dimension, size in zip(doc["id"], doc["size"]):
        positions = doc["dimension"][dimension]["category"]["index"]
        code = coords.get(dimension)
        position = positions[code] if code is not None else 0
        index = index * size + position
    return str(index)


def set_cell(doc, value, **coords):
    key = flat_index(doc, **coords)
    if value is None:
        doc["value"].pop(key, None)
    else:
        doc["value"][key] = value


class World:
    """Serves the two Eurostat queries from (editable) copies of the saved answers."""

    def __init__(self):
        self.cars = load("cars.json")
        self.homes = load("homes.json")
        self.fail = set()

    def fetch(self, url, **_):
        if url == eurostat.cars_url():
            if "cars" in self.fail:
                raise RuntimeError("could not reach Eurostat (test)")
            return json.dumps(self.cars).encode()
        if url == eurostat.homes_url():
            if "homes" in self.fail:
                raise RuntimeError("could not reach Eurostat (test)")
            return json.dumps(self.homes).encode()
        raise AssertionError(f"unexpected URL {url}")

    def copy(self):
        return copy.deepcopy(self)


@pytest.fixture
def world():
    return World()
