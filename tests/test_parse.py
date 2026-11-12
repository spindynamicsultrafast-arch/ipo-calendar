"""상세 페이지 파서 회귀 체크. 실행: python tests/test_parse.py"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from collect import diff, parse_detail  # noqa: E402

r = parse_detail(open(os.path.join(HERE, "fixtures", "38_2334.html"), encoding="utf-8").read())
assert (r["sub_start"], r["sub_end"]) == ("2026-11-10", "2026-11-11"), r
assert (r["demand_start"], r["demand_end"]) == ("2026-11-02", "2026-11-06"), r
assert r["pay"] == r["refund"] == "2026-11-13", r
assert r["listing"] == "2026-11-20", r
assert r["price"] == 5700 and (r["band_low"], r["band_high"]) == (4700, 5700), r
assert r["inst_ratio"] == 1051.38 and r["lockup_pct"] == 4.16, r
assert r["retail_ratio"] == 1851.14, r
assert r["status"] == "확정", r
assert r["code"] == "271160", r
assert (r["deposit_pct"], r["min_shares"]) == (50, 10), r

assert diff({"1": {"name": "A", "refund": "2026-11-13"}}, {"1": {"name": "A", "refund": "2026-11-14"}}) \
    == ["A refund: 2026-11-13 -> 2026-11-14"]
print("ok")

from collect import grade  # noqa: E402
assert grade(r) == "B"  # 1051:1, 상단, 확약 4.16% < 5
assert grade({**r, "lockup_pct": 6.0}) == "A"
assert grade({**r, "price": 5000.0}) == "C"
assert grade({**r, "inst_ratio": None}) is None
print("grade ok")
