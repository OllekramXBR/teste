"""Tests for the hand-written PDF writer.

A PDF that a reader refuses to open is worse than no export, and the part a
hand-written one usually gets wrong is the cross-reference table — every offset
is measured from the start of the file, in exactly ten digits, or the file is
unreadable. Most of these check the structure rather than the appearance.
"""

from __future__ import annotations

import re

import pytest

from app.pdf import LINES_PER_PAGE, build_pdf


@pytest.fixture
def chart() -> str:
    return "Tom: G maior\n\nD             G\nEra uma linha\n"


class TestStructure:
    def test_it_starts_and_ends_like_a_pdf(self, chart):
        data = build_pdf(chart, title="Uma")
        assert data.startswith(b"%PDF-1.4")
        assert data.rstrip().endswith(b"%%EOF")

    def test_every_object_is_listed_in_the_cross_reference_table(self, chart):
        data = build_pdf(chart)
        size = int(re.search(rb"/Size (\d+)", data).group(1))
        # One free entry plus one per object.
        assert data.count(b" 00000 n \n") == size - 1

    def test_every_offset_points_at_the_object_it_claims(self, chart):
        # The failure this catches is silent: readers that tolerate a wrong xref
        # hide it, and the ones that do not simply refuse the file.
        data = build_pdf(chart)
        entries = re.findall(rb"^(\d{10}) 00000 n $", data, re.MULTILINE)
        for number, offset in enumerate(entries, start=1):
            assert data[int(offset) :].startswith(f"{number} 0 obj".encode())

    def test_the_trailer_points_at_a_catalog(self, chart):
        data = build_pdf(chart)
        root = int(re.search(rb"/Root (\d+) 0 R", data).group(1))
        assert f"{root} 0 obj".encode() in data
        assert b"/Type /Catalog" in data

    def test_startxref_points_at_the_table(self, chart):
        data = build_pdf(chart)
        start = int(re.search(rb"startxref\n(\d+)", data).group(1))
        assert data[start:].startswith(b"xref")


class TestContent:
    def test_the_text_survives_into_the_file(self, chart):
        assert b"Era uma linha" in build_pdf(chart)

    def test_a_long_chart_is_paginated(self):
        data = build_pdf("\n".join(f"linha {n}" for n in range(LINES_PER_PAGE * 2 + 5)))
        assert int(re.search(rb"/Count (\d+)", data).group(1)) == 3

    def test_a_short_chart_is_one_page(self, chart):
        assert int(re.search(rb"/Count (\d+)", build_pdf(chart)).group(1)) == 1

    def test_parentheses_in_the_lyric_do_not_break_the_string(self):
        # An unescaped ')' ends a PDF string early and corrupts everything after.
        data = build_pdf("uma (coisa) qualquer")
        assert rb"\(coisa\)" in data

    def test_backslashes_are_escaped_too(self):
        assert rb"\\" in build_pdf("caminho\qualquer")

    def test_accents_survive(self):
        assert build_pdf("Vibração e coração")

    def test_the_degree_sign_becomes_something_printable(self):
        # Courier's standard encoding cannot draw every symbol; a chord must
        # degrade to a readable letter rather than vanish.
        data = build_pdf("B° C+ D7M")
        assert b"Bo" in data and b"C+" in data and b"D7M" in data

    def test_an_empty_chart_still_produces_a_valid_file(self):
        data = build_pdf("")
        assert data.startswith(b"%PDF") and b"/Type /Catalog" in data
