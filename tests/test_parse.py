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

import collect  # noqa: E402
collect.dart = lambda *a, **k: {"status": "000", "group": [{"title": "일반사항", "list": [
    {"rcept_no": "1", "sbd": "2026년 11월 20일 ~ 2026년 11월 21일", "pymd": "2026년 11월 25일"}]}]}
x = {"name": "A", "sub_start": "2026-11-19", "sub_end": "2026-11-20", "pay": "2026-11-25"}
assert collect.dart_check(x, {"A": "c"}) == "dart_fixed:청약 38=2026-11-19~2026-11-20", x
assert (x["sub_start"], x["sub_end"], x["pay"]) == ("2026-11-20", "2026-11-21", "2026-11-25"), x
assert collect.dart_check(x, {"A": "c"}) == "ok"
print("dart ok")

y = {"name": "A", "sub_start": "2026-11-20", "sub_end": "2026-11-21", "pay": "2026-11-24", "refund": "2026-11-24"}
assert collect.dart_check(y, {"A": "c"}) == "dart_fixed:납입 38=2026-11-24", y
assert (y["pay"], y["refund"]) == ("2026-11-25", "2026-11-25"), y  # 환불일도 같이
collect.dart = lambda *a, **k: {"status": "000", "group": [{"title": "일반사항", "list": [
    {"rcept_no": "1", "sbd": "2026년 11월 20일", "pymd": "2026년 11월 25일"}]}]}
z = {"name": "A", "sub_start": "2026-11-20", "sub_end": "2026-11-21", "pay": "2026-11-25", "refund": "2026-11-25"}
assert collect.dart_check(z, {"A": "c"}) == "ok" and z["sub_end"] == "2026-11-21", z  # 날짜 하나면 안 건드림
print("dart edge ok")

import json  # noqa: E402
cur = json.load(open(collect.os.path.join(collect.DATA, "ipos.json"), encoding="utf-8"))
assert collect.dead_fields(cur, "2026-11-15") == [], collect.dead_fields(cur, "2026-11-15")  # 실데이터는 통과
broken = {no: {**r, "inst_ratio": None} for no, r in cur.items()}
assert collect.dead_fields(broken, "2026-11-15") == ["inst_ratio"]
one = dict(cur); k = next(no for no, r in cur.items() if r["price"]); one[k] = {**cur[k], "inst_ratio": None}
assert collect.dead_fields(one, "2026-11-15") == []  # 한 종목만 빈 건 정상
print("fields ok")

# 철회: 목록에서 사라진 종목은 철회신고서가 있을 때만 '철회' 로 남김
collect.dart = lambda *a, **k: {"status": "000", "list": [{"report_nm": "철회신고서"}]}
old = {"1": {"name": "A", "sub_end": "2026-11-19", "status": "예정"},   # 사라짐 + 철회신고서
       "2": {"name": "B", "sub_end": "2026-11-19", "status": "예정"},   # 사라졌지만 DART 에 없는 회사
       "3": {"name": "A", "sub_end": "2026-10-01", "status": "예정"},   # 오래돼서 빠진 것
       "4": {"name": "B", "sub_end": "2026-11-19", "status": "철회"},   # 이미 철회로 찍힘 -> 조회 없이 유지
       "5": {"name": "A", "sub_end": "2026-11-19", "status": "예정"}}   # 목록에 그대로 있음
new = {"5": {"name": "A", "sub_end": "2026-11-19", "status": "확정"}}
collect.carry_withdrawn(old, new, "2026-11-03", {"A": "c"})
assert {no: r["status"] for no, r in new.items()} == {"5": "확정", "1": "철회", "4": "철회"}, new
assert grade(new["1"]) == "철회"
print("withdrawn ok")

# 표본 밖 기록: 백테스트 이후 상장 + 등급 있는 것만
g = {"price": 10000.0, "band_high": 10000.0, "inst_ratio": 900.0, "lockup_pct": 6.0}
md = collect.oos_md({"1": {**g, "name": "새것", "listing": "2026-11-16", "ohlc": {"o": 15000, "c": 8000}},
                     "2": {**g, "name": "옛것", "listing": "2026-11-12", "ohlc": {"o": 15000, "c": 8000}},
                     "3": {**g, "name": "장중", "listing": "2026-11-18", "ohlc": None}})
assert "| 2026-11-16 | 새것 | A | 900:1 | 6.00% | +50.0% | -20.0% |" in md and "| A | 1 | 0 | +50.0% | -20.0% |" in md, md
assert "옛것" not in md and "장중" not in md, md
print("oos ok")

# DART 누락 대조: 곧 청약하는 비상장사인데 목록에 없으면 경고. 상장사·스팩·아는 종목은 조용히
_soon = (collect.dt.date.today() + collect.dt.timedelta(days=5)).isoformat()
collect.dart = lambda path, corp_code, **k: {"status": "000", "list": [{"report_nm": "철회신고서"}] if corp_code == "gone" else [], "group": [
    {"title": "일반사항", "list": [{"rcept_no": "1", "corp_cls": "K" if corp_code == "listed" else "E", "corp_name": corp_code, "sbd": _soon}]},
    {"title": "증권의종류", "list": [{"slmthn": "주주배정" if corp_code == "rights" else "일반공모"}]}]}
collect.time.sleep = lambda s: None
w = collect.dart_missing({"아는것"}, {"아는것": "known", "새것": "new", "상장사": "listed", "무슨기업인수목적": "spac",
                                    "증자": "rights", "접음": "gone"})
assert len(w) == 1 and "new" in w[0], w
print("missing ok")

# 등급 입력값 대조: 38 숫자가 공시 본문에 있나
doc = ("확정공모가액 19,000원 기준 ... 수량 20,890,000 600,000 - 104,049,000 경쟁률 주2) 34.82 59.67 1.00 - 173.42 "
       "미확약 1 600,000 19,000 - - - 705 103,452,000 16,817 15일 확약 6개월 확약 9 587,000 19,375 합계 715 104,049,000")
ok = {"price": 19000.0, "inst_ratio": 173.42, "lockup_pct": 0.57}
assert collect.input_diffs(ok, doc) == [], collect.input_diffs(ok, doc)
assert collect.input_diffs({**ok, "price": 23000.0}, doc) == ["공모가"]
assert collect.input_diffs({**ok, "inst_ratio": 1173.42}, doc) == ["기관경쟁률"]  # 자릿수 하나 더 붙은 오타
assert collect.input_diffs({**ok, "lockup_pct": 5.7}, doc) == ["확약"]
print("inputs ok")
