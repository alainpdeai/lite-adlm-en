# -*- coding: utf-8 -*-
"""
Grader: the scale baseline still holds (Capacity and Performance P2).

Reads and writes here are whole-file: no pagination, one lock per list, every
edit rewrites every item. The live lists hold tens of items, so the question
"where is the knee?" had no answer. `tests/scale_probe.py` builds 1k and 5k
item lists in a throwaway data directory and measures; this file asserts.

The budgets below are deliberately an order of magnitude above what is measured
(5k read p50 is tens of ms). They are not precision thresholds — they are
guards against a *class* of regression:

  * a body-size cap that makes a whole-list write impossible (this system's only
    write path was refused with 413 at ~300 items until the limit was raised);
  * an accidental O(n^2) in validation, diffing or archival;
  * a probe that silently measures an empty list.

The third is what the payload-ratio check exists for: 5k items must produce a
payload several times larger than 1k's, or the probe never loaded the data and
every latency number would be measuring nothing.

What this grader deliberately does NOT decide: whether to add pagination or
virtual scrolling. The acceptance text says to optimise only at a real knee,
and at these numbers the server is not the knee — 5k items read in tens of
milliseconds. The payload (2.3 MiB at 5k) and the browser's DOM work are the
first real cost, and DOM render is NOT measured here (no headless browser);
see the probe's docstring. Conclusion as of this item: no pagination yet.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from grade_lib import Checker  # noqa: E402

c = Checker("scale-baseline")

PROBE = os.path.join(HERE, "scale_probe.py")

# Order-of-magnitude guards, not precision thresholds (see module docstring).
READ_BUDGET_MS = 2000.0        # 5k read p50 measured in the tens of ms
WRITE_BUDGET_MS = 3000.0       # 5k one-item write p50 measured ~200ms
PAYLOAD_RATIO_MIN = 3.0        # 5k payload must dwarf 1k's, or nothing was loaded


def run_probe():
    p = subprocess.run([sys.executable, PROBE], capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=900)
    out = (p.stdout or "") + (p.stderr or "")
    line = None
    for l in out.splitlines():
        if l.startswith("JSON "):
            line = l[5:]
    if not line:
        return None, out
    try:
        return json.loads(line), out
    except ValueError:
        return None, out


def _check_probe_result(c, data, out):
    c.check("the scale probe produced a result", data is not None,
            out.strip().splitlines()[-5:])
    return data is not None


def _check_both_scales(c, scales):
    c.check("both scales were measured (1k and 5k)",
            set(scales) >= {1000, 5000}, sorted(scales))
    return 5000 in scales and 1000 in scales


def _check_scale_budgets(c, s1, s5):
    # The write path must scale far enough to hold the list at all.
    c.check("a 5k-item list can be written at all (a body-size cap would turn "
            "this into 413, and a whole-list write is the only write there is)",
            s5["bulk_write_s"] is not None and s5["bulk_write_s"] > 0,
            s5.get("bulk_write_s"))

    # Guard against measuring an empty shell.
    b1, b5 = s1["payload_bytes"] or 0, s5["payload_bytes"] or 0
    c.check("the 5k payload is several times the 1k payload (the probe really "
            "loaded 5x the items — otherwise every timing below measures "
            "nothing)",
            b1 > 0 and b5 / float(b1) >= PAYLOAD_RATIO_MIN,
            (b1, b5, round(b5 / float(b1), 2) if b1 else None))

    c.check("1k read p50 is within budget",
            s1["read"]["p50_ms"] is not None and s1["read"]["p50_ms"] <= READ_BUDGET_MS,
            s1["read"])
    c.check("5k read p50 is within budget (order-of-magnitude guard, not a "
            "precision threshold)",
            s5["read"]["p50_ms"] is not None and s5["read"]["p50_ms"] <= READ_BUDGET_MS,
            s5["read"])
    c.check("5k one-item write p50 is within budget (every edit rewrites the "
            "whole file)",
            s5["write_one_item"]["p50_ms"] is not None
            and s5["write_one_item"]["p50_ms"] <= WRITE_BUDGET_MS,
            s5["write_one_item"])

    # Contrast: scale must actually cost something. If 5k were as fast as 1k the
    # payload check would already have failed; this one pins the direction.
    c.check("5k is not faster than 1k (the measurement is sensitive to scale)",
            s5["read"]["p50_ms"] >= s1["read"]["p50_ms"] * 0.5,
            (s1["read"]["p50_ms"], s5["read"]["p50_ms"]))

    c.check("the client-side parse cost is recorded for both scales",
            s1["client_parse"]["p50_ms"] is not None
            and s5["client_parse"]["p50_ms"] is not None,
            (s1["client_parse"], s5["client_parse"]))

    print()
    print("  baseline: 1k read %sms / payload %s KiB / write %sms | "
          "5k read %sms / payload %s KiB / write %sms"
          % (s1["read"]["p50_ms"], s1["payload_kib"], s1["write_one_item"]["p50_ms"],
             s5["read"]["p50_ms"], s5["payload_kib"], s5["write_one_item"]["p50_ms"]))
    print("  DOM render is NOT measured here (no headless browser) — see the "
          "probe docstring.")


def main():
    data, out = run_probe()
    if not _check_probe_result(c, data, out):
        c.finish()

    scales = {s["items"]: s for s in data.get("scales", [])}
    if not _check_both_scales(c, scales):
        c.finish()

    s1, s5 = scales[1000], scales[5000]
    _check_scale_budgets(c, s1, s5)
    c.finish()


if __name__ == "__main__":
    main()
