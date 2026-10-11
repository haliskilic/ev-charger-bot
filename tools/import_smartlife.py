"""Import the Smart Life "Record" export into the sessions table so history and comparisons are available from day one.

Accepts either the original .xlsx exported by Smart Life (Device → Record → export) or a CSV with the columns
start,end,duration_min,energy_kwh (ISO timestamps). The export repeats every row many times; duplicates are removed.

Usage:  python -m tools.import_smartlife path/to/export.xlsx
Running it again is safe: records that already exist are skipped. Cost uses the current single price.
"""

from __future__ import annotations

import csv
import re
import sys
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime

from evsarj import config
from evsarj.db import DB

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def read_xlsx(path: str) -> set[tuple[str, str, int, float]]:
    z = zipfile.ZipFile(path)
    shared: list[str] = []
    if "xl/sharedStrings.xml" in z.namelist():
        for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("m:si", NS):
            shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
    recs: set[tuple[str, str, int, float]] = set()
    for row in ET.fromstring(z.read("xl/worksheets/sheet1.xml")).iter("{%s}row" % NS["m"]):
        vals: list[str | None] = []
        for c in row.findall("m:c", NS):
            v = c.find("m:v", NS)
            isv = c.find("m:is", NS)
            if v is None:
                vals.append("".join(x.text or "" for x in isv.iter("{%s}t" % NS["m"])) if isv is not None else None)
            elif c.get("t") == "s":
                vals.append(shared[int(v.text)])
            else:
                vals.append(v.text)
        if len(vals) >= 5 and vals[1] and re.match(r"\d{4}/\d\d/\d\d \d\d:\d\d", vals[1]):
            start = datetime.strptime(vals[1], "%Y/%m/%d %H:%M")
            end = datetime.strptime(vals[2], "%Y/%m/%d %H:%M")
            m = re.match(r"(\d+)hour(\d+)minute", vals[3] or "")
            dur = int(m.group(1)) * 60 + int(m.group(2)) if m else int((end - start).total_seconds() // 60)
            recs.add((start.isoformat(), end.isoformat(), dur, float(vals[4])))
    return recs


def read_csv(path: str) -> set[tuple[str, str, int, float]]:
    recs: set[tuple[str, str, int, float]] = set()
    with open(path, encoding="utf-8", newline="") as f:
        for row in csv.DictReader(f):
            start = row.get("start") or row.get("baslangic")
            end = row.get("end") or row.get("bitis")
            dur = row.get("duration_min") or row.get("sure_dk")
            energy = row.get("energy_kwh") or row.get("enerji_kwh")
            recs.add((start, end, int(dur), float(energy)))
    return recs


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("usage: python -m tools.import_smartlife export.xlsx|records.csv")
    path = sys.argv[1]
    recs = read_xlsx(path) if path.lower().endswith(".xlsx") else read_csv(path)
    settings, _ = config.load()
    db = DB(config.BASE_DIR / settings.db_path)
    settings.apply_overrides(db.all_settings())
    tz = settings.tz
    price = settings.tariff.single
    added = skipped = 0
    for start_s, end_s, dur, energy in sorted(recs):
        start = datetime.fromisoformat(start_s).replace(tzinfo=tz).timestamp()
        end = datetime.fromisoformat(end_s).replace(tzinfo=tz).timestamp()
        if db.has_import(start, end):
            skipped += 1
            continue
        sid = db.create_session(start, source="smartlife")
        db.update_session(
            sid, unplug_ts=end, plugged_s=dur * 60, energy_kwh=energy, energy_device_kwh=energy,
            cost=round(energy * price, 2), end_reason="smartlife", closed=1,
        )
        added += 1
    print(f"imported: {added}, already present: {skipped}, lifetime total: {db.lifetime_kwh():.2f} kWh")


if __name__ == "__main__":
    main()
