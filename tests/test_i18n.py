"""Every English string must have a Turkish counterpart with the same placeholders, and formatting must be locale-correct."""

from __future__ import annotations

import re
import unittest
from zoneinfo import ZoneInfo

from evsarj.fmt import Formatter
from evsarj.i18n import EN, TR, Lang

PLACEHOLDER = re.compile(r"\{(\w+)")


class CatalogueTests(unittest.TestCase):
    def test_turkish_covers_english(self):
        missing = sorted(set(EN) - set(TR))
        self.assertEqual(missing, [], f"missing Turkish keys: {missing}")

    def test_placeholders_match(self):
        for key, en in EN.items():
            tr = TR.get(key, en)
            self.assertEqual(set(PLACEHOLDER.findall(en)), set(PLACEHOLDER.findall(tr)), f"placeholder mismatch in {key}")

    def test_fallback_and_formatting(self):
        L = Lang("tr")
        self.assertEqual(L("plugged", time="18:13", amps=32, mode="anında şarj").splitlines()[0], "🔌 <b>Araç takıldı</b> · 18:13")
        self.assertEqual(Lang("xx").code, "en")


class FormatterTests(unittest.TestCase):
    def test_numbers(self):
        tz = ZoneInfo("Europe/Istanbul")
        en = Formatter("en", tz, "€")
        tr = Formatter("tr", tz, "TL")
        self.assertEqual(en.num(1234.5, 1), "1,234.5")
        self.assertEqual(tr.num(1234.5, 1), "1.234,5")
        self.assertEqual(en.pct(38.4), "38%")
        self.assertEqual(tr.pct(38.4), "%38")
        self.assertEqual(tr.pct(12, signed=True), "+%12")
        self.assertEqual(en.money(32.93), "32.93 €")
        self.assertEqual(tr.money(32.93), "32,93 TL")

    def test_durations(self):
        tz = ZoneInfo("UTC")
        en = Formatter("en", tz)
        tr = Formatter("tr", tz)
        self.assertEqual(en.duration(45), "45 s")
        self.assertEqual(en.duration(655), "11 min")
        self.assertEqual(en.duration(3600 * 2 + 60 * 5), "2 h 5 min")
        self.assertEqual(tr.duration(3600 * 2 + 60 * 5), "2 sa 5 dk")
        self.assertEqual(tr.duration(90000), "1 gün 1 sa")


if __name__ == "__main__":
    unittest.main()
