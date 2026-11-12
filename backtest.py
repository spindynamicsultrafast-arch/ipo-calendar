"""등급 vs 상장 첫날 수익률 백테스트. 사용: python backtest.py [페이지수=6]

38 '신규상장' 목록(시초가·첫날종가)과 상세 페이지(수요예측 결과)를 묶어
grade() 등급별 수익률을 본다. 스팩 제외. 결과는 data/backtest.json 에 캐시.
"""
import json
import os
import re
import statistics as st
import sys
import time

from collect import BASE, DATA, get, grade, num, parse_detail

CACHE = os.path.join(DATA, "backtest.json")


def listed_rows(page):
    html = get(f"{BASE}/html/fund/index.htm?o=nw&page={page}")
    out = []
    for row in re.findall(r"<tr[^>]*>(.*?)</tr>", html, flags=re.S):
        m = re.search(r"o=v&amp;no=(\d+)", row)
        cells = [re.sub(r"\s+", " ", re.sub(r"<[^>]+>|&nbsp;", " ", c)).strip()
                 for c in re.findall(r"<td[^>]*>(.*?)</td>", row, flags=re.S)]
        # 기업명, 상장일, 현재가, 전일비, 공모가, 공모가대비, 시초가, 시초/공모, 첫날종가
        if not m or len(cells) < 9 or "<table" in row:
            continue
        won = lambda s: num(s) if re.fullmatch(r"[\d,]+", s) else None  # '-', '예정' 등은 None
        name, ipo, open_, close1 = cells[0], won(cells[4]), won(cells[6]), won(cells[8])
        if "스팩" in name or not (ipo and open_ and close1):
            continue
        out.append(dict(no=m.group(1), name=name, listed=cells[1], ipo=ipo,
                        open_ret=round((open_ / ipo - 1) * 100, 1), close_ret=round((close1 / ipo - 1) * 100, 1)))
    return out


def main(pages=6):
    sys.stdout.reconfigure(encoding="utf-8")
    cache = json.load(open(CACHE, encoding="utf-8")) if os.path.exists(CACHE) else {}
    for p in range(1, pages + 1):
        for row in listed_rows(p):
            if row["no"] not in cache:
                cache[row["no"]] = {**row, **parse_detail(get(f"{BASE}/html/fund/?o=v&no={row['no']}"))}
                time.sleep(0.5)
    os.makedirs(DATA, exist_ok=True)
    json.dump(cache, open(CACHE, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    rows = [r for r in cache.values() if grade(r)]
    print(f"표본 {len(rows)}종목 ({min(r['listed'] for r in rows)} ~ {max(r['listed'] for r in rows)})\n")
    print("등급  n   시초 중앙값  시초 평균  시초<0 비율  첫날종가 중앙값")
    for g in "ABC":
        xs = [r for r in rows if grade(r) == g]
        if not xs:
            continue
        o = [r["open_ret"] for r in xs]
        c = [r["close_ret"] for r in xs]
        print(f"  {g}  {len(xs):3d}  {st.median(o):9.1f}%  {st.mean(o):8.1f}%  "
              f"{sum(v < 0 for v in o) / len(o) * 100:9.0f}%  {st.median(c):12.1f}%")


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 6)
