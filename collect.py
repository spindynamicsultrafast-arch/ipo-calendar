"""공모주 일정 수집기 (v0).

38커뮤니케이션 목록 + 상세 페이지에서 일정/수요예측 결과를 모아 data/ipos.json 에 저장.
OpenDART 키가 .env(DART_API_KEY) 에 있으면 청약일·납입일을 증권신고서와 대조한다.
직전 실행과 비교해 일정이 바뀐 종목은 data/changes.log 에 남긴다.

사용: python collect.py
"""
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://www.38.co.kr"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
DATE_KEYS = ("demand_start", "demand_end", "sub_start", "sub_end", "pay", "refund", "listing")
UA = {"User-Agent": "Mozilla/5.0"}


def get(url, enc="cp949"):
    req = urllib.request.Request(url, headers=UA)
    return urllib.request.urlopen(req, timeout=20).read().decode(enc, "ignore")


def flat(html):
    """HTML 을 '라벨| 값| 라벨| 값' 형태 한 줄 텍스트로."""
    s = re.sub(r"<script.*?</script>|<style.*?</style>|<!--.*?-->", "", html, flags=re.S)
    s = re.sub(r"</t[dhr]>", "|", s)
    s = re.sub(r"<[^>]+>|&nbsp;", " ", s)
    s = re.sub(r"\s+", " ", s)
    return re.sub(r"(\s*\|)+\s*", "| ", s)


def num(s):
    return float(s.replace(",", "")) if s else None


def ymd(y, m, d):
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def rng(label, t):
    """'라벨| 2026.11.10 ~ 2026.11.11' -> (start, end). 단일 날짜면 start == end."""
    m = re.search(label + r"\| (\d{4})\.(\d{2})\.(\d{2})(?: ~ (\d{4})\.(\d{2})\.(\d{2}))?", t)
    if not m:
        return None, None
    a = ymd(*m.group(1, 2, 3))
    return a, (ymd(*m.group(4, 5, 6)) if m.group(4) else a)


def parse_detail(html):
    t = flat(html)
    f = lambda pat: (m.group(1) if (m := re.search(pat, t)) else None)
    rec = {}
    rec["demand_start"], rec["demand_end"] = rng("수요예측일", t)
    rec["sub_start"], rec["sub_end"] = rng("공모청약일", t)
    rec["pay"], _ = rng("납입일", t)
    rec["refund"], _ = rng("환불일", t)
    rec["listing"], _ = rng(r"상장일", t)
    rec["price"] = num(f(r"확정공모가\| ([\d,]+) 원"))
    band = re.search(r"희망공모가액 : ([\d,]+) ~ ([\d,]+) 원", t)
    rec["band_low"], rec["band_high"] = (num(band.group(1)), num(band.group(2))) if band else (None, None)
    rec["inst_ratio"] = num(f(r"기관경쟁률\| ([\d,.]+)"))  # ':1' 이 붙거나 안 붙음
    rec["lockup_pct"] = num(f(r"의무보유확약\| ([\d.]+)%"))
    rec["retail_ratio"] = num(f(r"청약경쟁률\| ([\d,.]+):1"))
    rec["amount_mil"] = num(f(r"공모금액 : ([\d,]+) \(백만원\)"))
    rec["sector"] = f(r"업종\| ([^|]+?)\|")
    rec["underwriter"] = f(r"주간사\| ([^|]+?)\|")
    rec["code"] = f(r"종목코드\| (\w{6})\|")
    rec["deposit_pct"] = num(f(r"일반청약자\| [^|]*\| 청약증거금율 : (\d+)%")) or 50
    rec["min_shares"] = num(f(r"일반청약자\|(?:[^|]*\|){3} 최저 : ([\d,]+) 주")) or 10  # 38에 '-'면 관행 10주
    if rec["inst_ratio"] is None:  # 수요예측 전엔 38이 확약 0%로 표시함
        rec["lockup_pct"] = None
    rec["status"] = "확정" if rec["price"] else "예정"
    return rec


def grade(rec):
    """v0 수급·가격 등급. 수요예측 전이면 None. 기준은 PLAN.md 참고."""
    if rec["inst_ratio"] is None or not rec["price"] or not rec["band_high"]:
        return None
    top = rec["price"] >= rec["band_high"]
    if not top or rec["inst_ratio"] < 400:
        return "C"
    if rec["inst_ratio"] >= 800 and (rec["lockup_pct"] or 0) >= 5:
        return "A"
    return "B"


def list_rows(html):
    """목록 페이지 -> [(no, name)]."""
    pat = r'href="/html/fund/\?o=v&amp;no=(\d+)[^"]*"><font[^>]*>([^<]+)</font>'
    return [(no, name.strip()) for no, name in re.findall(pat, html)]


def ohlc(code, day):
    """네이버 일봉에서 그 날짜의 시가·고가·저가·종가."""
    x = get(f"https://fchart.stock.naver.com/sise.nhn?symbol={code}&timeframe=day&count=300&requestType=0", "euc-kr")
    m = re.search(rf'data="{day.replace("-", "")}\|(\d+)\|(\d+)\|(\d+)\|(\d+)\|', x)
    return dict(zip("ohlc", map(int, m.groups()))) if m else None


def naver_code(name):
    r = json.loads(get("https://ac.stock.naver.com/ac?" + urllib.parse.urlencode({"q": name, "target": "stock"}), "utf-8"))
    return next((i["code"] for i in r.get("items", []) if norm(i["name"]) == norm(name)), None)  # "(Reg.S)" 같은 꼬리 무시


def history(year):
    """그 해 상장한 종목 전부 (38 신규상장 목록) + 상장일 OHLC. data/history.json 캐시."""
    from backtest import listed_rows  # backtest 가 collect 를 import 하므로 여기서
    path = os.path.join(DATA, "history.json")
    cache = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    today = dt.date.today().isoformat()
    for page in range(1, 20):
        rows = listed_rows(page)
        for row in rows:
            if not row["listed"].startswith(year) or cache.get(row["no"], {}).get("ohlc"):
                continue
            rec = parse_detail(get(f"{BASE}/html/fund/?o=v&no={row['no']}"))
            time.sleep(0.5)
            rec.update(name=row["name"], no=row["no"], source=f"{BASE}/html/fund/?o=v&no={row['no']}",
                       listing=rec["listing"] or row["listed"].replace("/", "-"))
            # 상장 당일 봉은 장중이라 미완성 -> 다음 실행에 다시 받음
            if rec["listing"] < today:
                rec["ohlc"] = rec["code"] and ohlc(rec["code"], rec["listing"])
                if not rec["ohlc"]:  # 38 종목코드가 상장 전 임시값(9xxxxx)인 경우가 있음 -> 이름으로 실제 코드
                    rec["code"] = naver_code(row["name"]) or rec["code"]
                    rec["ohlc"] = ohlc(rec["code"], rec["listing"])
            cache[row["no"]] = rec
        if not rows or min(r["listed"] for r in rows) < year:
            break
    json.dump(cache, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    return {no: r for no, r in cache.items() if (r["listing"] or "").startswith(year)}


# ---------- OpenDART 대조 ----------

def load_env():
    p = os.path.join(HERE, ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if "=" in line and not line.lstrip().startswith("#"):
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"'))


def dart(path, **q):
    q["crtfc_key"] = os.environ["DART_API_KEY"]
    url = f"https://opendart.fss.or.kr/api/{path}?{urllib.parse.urlencode(q)}"
    return json.loads(get(url, "utf-8"))


def norm(name):
    return re.sub(r"\(.*?\)|주식회사|\s", "", name)


def dart_filers(days=89):  # corp_code 없으면 DART 검색 기간 최대 3개월
    """최근 증권신고서(지분증권) 제출 회사 {정규화이름: corp_code}."""
    end = dt.date.today()
    bgn = end - dt.timedelta(days=days)
    out, page = {}, 1
    while True:
        r = dart("list.json", bgn_de=bgn.strftime("%Y%m%d"), end_de=end.strftime("%Y%m%d"),
                 pblntf_detail_ty="C001", page_no=page, page_count=100)
        if r.get("status") != "000":
            break
        for it in r["list"]:
            out.setdefault(norm(it["corp_name"]), it["corp_code"])
        if page >= int(r.get("total_page", 1)):
            break
        page += 1
    return out


def dates_in(s):
    return [ymd(*m) for m in re.findall(r"(\d{4})\D{1,3}(\d{1,2})\D{1,3}(\d{1,2})", s or "")]


def dart_check(rec, filers):
    """증권신고서의 청약기일·납입기일과 38 값 비교. 결과: ok / mismatch:... / not_found / error:..."""
    code = filers.get(norm(rec["name"]))
    if not code:
        return "not_found"
    end = dt.date.today() + dt.timedelta(days=1)
    r = dart("estkRs.json", corp_code=code, bgn_de=(end - dt.timedelta(days=150)).strftime("%Y%m%d"),
             end_de=end.strftime("%Y%m%d"))
    if r.get("status") != "000":
        return f"error:{r.get('status')} {r.get('message')}"
    general = next((g["list"] for g in r.get("group", []) if g.get("title") == "일반사항"), [])
    if not general:
        return "error:일반사항 없음"
    latest = max(general, key=lambda x: x["rcept_no"])  # 가장 최근 정정본
    sbd, pymd = dates_in(latest.get("sbd")), dates_in(latest.get("pymd"))
    bad = []
    if sbd and (sbd[0], sbd[-1]) != (rec["sub_start"], rec["sub_end"]):
        bad.append(f"청약 DART={sbd[0]}~{sbd[-1]}")
    if pymd and pymd[0] != rec["pay"]:
        bad.append(f"납입 DART={pymd[0]}")
    return "mismatch:" + "; ".join(bad) if bad else "ok"


# ---------- 실행 ----------

def diff(old, new):
    out = []
    for no, rec in new.items():
        prev = old.get(no)
        if not prev:
            continue
        for k in DATE_KEYS + ("price", "status"):
            if prev.get(k) != rec.get(k):
                out.append(f"{rec['name']} {k}: {prev.get(k)} -> {rec.get(k)}")
    return out


def render(recs):
    """calendar.html 안의 <script id="ipo-data"> 블록을 최신 데이터로 교체. 스팩 제외."""
    path = os.path.join(HERE, "calendar.html")
    keys = ("name", "sub_start", "sub_end", "refund", "listing", "price", "band_low", "band_high",
            "inst_ratio", "lockup_pct", "retail_ratio", "underwriter", "sector", "dart", "source", "ohlc", "deposit_pct", "min_shares")
    items = [{**{k: r.get(k) for k in keys}, "grade": grade(r)}
             for r in sorted(recs.values(), key=lambda r: r["sub_start"]) if "스팩" not in r["name"]]
    blob = json.dumps({"generated_at": dt.datetime.now().isoformat(timespec="minutes"), "items": items},
                      ensure_ascii=False).replace("</", "<\\/")
    html = open(path, encoding="utf-8").read()
    html = re.sub(r'(<script id="ipo-data" type="application/json">).*?(</script>)',
                  lambda m: m.group(1) + blob + m.group(2), html, count=1, flags=re.S)
    open(path, "w", encoding="utf-8").write(html)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    load_env()
    today = dt.date.today()
    keep_from = (today - dt.timedelta(days=14)).isoformat()

    recs = {}
    for no, name in list_rows(get(f"{BASE}/html/fund/index.htm?o=k")):
        rec = parse_detail(get(f"{BASE}/html/fund/?o=v&no={no}"))
        time.sleep(0.5)  # 사이트 부담 줄이기
        if not rec["sub_end"] or rec["sub_end"] < keep_from:
            continue
        rec.update(name=name, no=no, source=f"{BASE}/html/fund/?o=v&no={no}",
                   fetched_at=dt.datetime.now().isoformat(timespec="seconds"))
        recs[no] = rec

    if os.environ.get("DART_API_KEY"):
        try:
            filers = dart_filers()
        except Exception as e:  # DART 접속 장애(타임아웃)로 페이지 갱신 전체가 멈추지 않게
            print("DART 목록 실패:", e)
            filers = {}
        for rec in recs.values():
            try:
                rec["dart"] = dart_check(rec, filers)
            except Exception as e:  # DART 장애가 수집 전체를 막지 않게
                rec["dart"] = f"error:{e}"
    else:
        for rec in recs.values():
            rec["dart"] = "no_key"

    path = os.path.join(DATA, "ipos.json")
    old = json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
    changes = diff(old, recs)
    os.makedirs(DATA, exist_ok=True)
    json.dump(recs, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if changes:
        with open(os.path.join(DATA, "changes.log"), "a", encoding="utf-8") as fp:
            for c in changes:
                fp.write(f"{dt.datetime.now():%Y-%m-%d %H:%M} {c}\n")
    hist = history(str(today.year))
    for no, r in recs.items():
        r["ohlc"] = hist.get(no, {}).get("ohlc")
    render({**hist, **recs})

    s = lambda v: "-" if v is None else v  # 0% 확약도 0 으로 보이게
    for r in sorted(recs.values(), key=lambda r: r["sub_start"]):
        print(f"{r['sub_start']}~{r['sub_end'][5:]} 환불 {s(r['refund'])} 상장 {s(r['listing'])} "
              f"[{r['status']}] {r['name']} 기관 {s(r['inst_ratio'])}:1 확약 {s(r['lockup_pct'])}% "
              f"DART {r['dart']}")
    print(f"\n{len(recs)}종목, 변경 {len(changes)}건")
    for c in changes:
        print(" *", c)


if __name__ == "__main__":
    main()
