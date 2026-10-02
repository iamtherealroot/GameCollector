#!/usr/bin/env python3
"""Regression checks for logical collection counting."""
import sys
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.app import logical_collection_unit_key


def row(category, title, edition=None, external_id=None, external_source=None, barcode=None):
    return SimpleNamespace(category=category, title=title, edition=edition, external_id=external_id, external_source=external_source, barcode=barcode)


ncis_a = row("tv", "Navy CIS Staffel 8.1", "Staffel 8.1")
ncis_b = row("tv", "Navy CIS Staffel 8.2", "Staffel 8.2")
assert logical_collection_unit_key(ncis_a, {}) == "season:8"
assert logical_collection_unit_key(ncis_b, {}) == "season:8"
assert len({logical_collection_unit_key(ncis_a, {}), logical_collection_unit_key(ncis_b, {})}) == 1
film_a = row("movies", "Film A", external_id="42", external_source="TMDB")
film_b = row("movies", "Film A Steelbook", external_id="42", external_source="TMDB")
assert logical_collection_unit_key(film_a, {}) == logical_collection_unit_key(film_b, {})
book_a = row("books", "Band Eins", barcode="9780000000001")
book_b = row("books", "Band Eins Taschenbuch", barcode="9780000000001")
assert logical_collection_unit_key(book_a, {}, 1) == logical_collection_unit_key(book_b, {}, 1)
print("OK: logische Staffel-, Film- und Bandzählung")
