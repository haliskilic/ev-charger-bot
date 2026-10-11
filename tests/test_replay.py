"""Regression test: the recorded discovery session of 2026-10-11 must produce exactly the expected event sequence.

The fixture is a real capture from a Hici 22 kW charger (Tuya qccdz, protocol 3.4): reboot, unplug, plug-in,
charging, manual stop/resume from the app, car-side stop, unlock with 0 A "charging", unplug with the DP25 counter.
"""

from __future__ import annotations

import os
import tempfile
import unittest

from tools.replay import replay

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "discovery_2026-10-11.jsonl")


class ReplayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sink, cls.db = replay(FIXTURE, os.path.join(tempfile.gettempdir(), "evsarj-test-replay.db"), lang="en", verbose=False)

    def test_event_sequence(self):
        types_ = [e[1] for e in self.sink.events]
        self.assertEqual(types_, [
            "rebooted",          # 18:07 power cycle: free + 6 A signature, no false "unplugged"
            "unplugged",         # 18:10 cable removed (short summary, no charging)
            "plugged",           # 18:13
            "charging_started",  # 18:13 power > 0
            "stopped",           # 18:17 switch off from the app (no duplicate resume/stop pair)
            "resumed",           # 18:19
            "car_stopped",       # 18:22 car ended charging abruptly
            "unplugged",         # 18:24 with DP25 = 0.56 kWh; no false "device record closed"
            "plugged",           # 18:31 brief plug-in
            "unplugged",         # 18:31
        ])

    def test_session_values(self):
        rows = [dict(r) for r in self.db.all_sessions()]
        self.assertEqual(len(rows), 3)
        s = rows[1]
        self.assertEqual(s["end_reason"], "car_stopped")
        self.assertAlmostEqual(s["energy_kwh"], 0.56, places=2)  # charger counter wins
        self.assertTrue(0.45 <= s["energy_calc_kwh"] <= 0.60)
        self.assertAlmostEqual(s["peak_kw"], 4.669, places=2)
        self.assertTrue(400 <= s["charge_s"] <= 480)
        self.assertEqual(rows[0]["end_reason"], "no_charge")
        self.assertEqual(rows[2]["end_reason"], "no_charge")
        segs = [dict(r) for r in self.db.q("SELECT * FROM segments ORDER BY id")]
        self.assertEqual([x["end_reason"] for x in segs], ["manual_stop", "car_stopped"])

    def test_summary_text_in_english(self):
        text = [e[2] for e in self.sink.events if e[1] == "unplugged"][1]
        self.assertIn("Session summary", text)
        self.assertIn("0.56 kWh (charger counter)", text)
        self.assertIn("End reason: car ended charging", text)


if __name__ == "__main__":
    unittest.main()
