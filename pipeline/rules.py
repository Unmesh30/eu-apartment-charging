"""Why now: Germany's tighter building rules on EV charging, written down from published summaries.

This is a rule, not a data feed, so it carries the date it was last checked. Every point below is
stated the same way by the German Chambers of Commerce (DIHK) and IHK summaries of the amended
GEIG; nothing here goes beyond what they say.
"""

GERMANY_2027 = {
    "country": "DE",
    "starts": "2027-01-01",
    "title": "Germany 2027",
    "points": [
        "New apartment buildings with more than 3 parking spaces: pre-cable at least half of the spaces "
        "and put in at least one charging point.",
        "Major renovations that include the car park or its wiring: pre-cable at least half of the spaces, "
        "also from 4 spaces.",
        "New or replaced charging points under the law must support smart charging on open, "
        "non-proprietary standards.",
    ],
    "limit": "Existing buildings that aren't renovated get no new duty from this law.",
    "law": "Amended GEIG, published 28 July 2026; carries over EU directive 2024/1275.",
    "sources": [
        {
            "label": "DIHK summary",
            "url": "https://www.dihk.de/de/serviceportal/fuer-gewerbetreibende-unternehmer/"
            "elektromobilitaetsinfrastruktur-an-gebaeuden-das-gilt-ab-2027-192330",
        },
        {
            "label": "IHK Freiburg",
            "url": "https://www.ihk.de/freiburg/unternehmen-beraten/umwelt-energie-und-klimaschutz/"
            "energie-und-klimaschutz/geig-novelle-7217958",
        },
    ],
    "checked": "2026-11-21",
}
