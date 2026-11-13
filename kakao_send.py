"""오늘 공모주 일정(+다음 일정)을 사진으로 찍어 카톡 PC 앱 채팅방에 보낸다.

사용:
  python kakao_send.py --shot             # 사진만 만들고 경로 출력 (안 보냄)
  python kakao_send.py                    # 사진 전송
  python kakao_send.py --week             # 다음 주 월~금 미리보기 (일요일 예약용)
  옵션: --to "방이름[;방이름]" (기본 손정우 = 나와의 채팅), --date 2026-11-16  (단톡방 이름에 쉼표가 있어 ; 로 나눔)

휴장일(주말·CLOSED)과 오늘 A/B 일정 없는 날은 안 보낸다. 사진 = 오늘 + 그다음 가장 빠른 일정.
조건: PC 켜짐·잠금 해제, 카톡 PC 앱 로그인. 방 창이 없으면 메인 창 채팅 탭에서
이름 검색해 연다. 창·입력칸 포커스를 확인 못 하면 키를 안 누른다.
카톡은 WM_SETTEXT 로 넣은 글은 Enter 로 안 보낸다. 진짜 Ctrl+V·Enter 만 먹는다 (2026-11-12 확인).
"""
import ctypes
import datetime as dt
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
import urllib.request
from ctypes import wintypes as W

from PIL import Image, ImageChops

URL = "https://spindynamicsultrafast-arch.github.io/ipo-calendar/"
SHOW = {"A", "B"}  # 페이지 기본 필터와 같게: C·대기 제외
CHROME = r"C:\Program Files\Google\Chrome\Application\chrome.exe"
# 주말 말고 증시 휴장일. 2027 은 우주항공청 월력요항(2026-06-29) 기준 + 연말 휴장(12/31) 추정.
# ponytail: 손으로 관리. 선거일·임시공휴일 등 기타 휴장은 거래소 공지 나면 여기 추가. 2028 은 2027 하반기에 추가
CLOSED = set("""
2026-12-25 2026-12-31
2027-01-01 2027-02-08 2027-02-09 2027-03-01 2027-05-03 2027-05-05 2027-05-13 2027-07-19
2027-08-16 2027-09-14 2027-09-15 2027-09-16 2027-10-04 2027-10-11 2027-12-27 2027-12-31
""".split())
u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
k32.GlobalAlloc.restype = k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
u32.SetClipboardData.argtypes = [W.UINT, ctypes.c_void_p]


HERE = os.path.dirname(os.path.abspath(__file__))
OPEN_DAYS = os.path.join(HERE, "open_days.json")  # KIS 휴장일조회 결과 사본 {"YYYYMMDD": 개장여부}
ALERT_TO = "손정우"  # 실패 알림 받을 방 (나와의 채팅)


def sync_open_days():
    """overnight-kis VM 의 KIS 개장일 캐시(약 45~96일치)를 읽기 전용으로 받아 둔다. 일요일 --week 때 한 번."""
    r = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "kis",
                        "cat overnight-kis/app/data/open_days.json"], capture_output=True, timeout=60)
    cal = json.loads(r.stdout.decode("utf-8"))  # 실패하면 여기서 던짐 → 실패 알림
    with open(OPEN_DAYS, "w", encoding="utf-8") as f:
        json.dump(cal, f)


def is_open(d):
    """KIS 달력이 그 날을 덮으면 그걸 믿고, 아니면 주말 + 손 목록(CLOSED)."""
    try:
        with open(OPEN_DAYS, encoding="utf-8") as f:
            v = json.load(f).get(d.strftime("%Y%m%d"))
        if v is not None:
            return v
    except (OSError, ValueError):
        pass
    return d.weekday() < 5 and d.isoformat() not in CLOSED


def has_events(day, week=False):
    """보낼 일정이 있나. 평소: 오늘 A/B. week: 다음 주 월~금 A/B 또는 평가 전 청약."""
    html = urllib.request.urlopen(URL, timeout=20).read().decode("utf-8")
    items = json.loads(re.search(r'<script id="ipo-data" type="application/json">(.*?)</script>', html, re.S)
                       .group(1).replace("<\\/", "</"))["items"]
    days = [day]
    if week:
        mon = dt.date.fromisoformat(day)
        mon += dt.timedelta(days=7 - mon.weekday())
        days = [(mon + dt.timedelta(days=i)).isoformat() for i in range(5)]
    sub = lambda it, d: it.get("sub_start") and it["sub_start"] <= d <= it["sub_end"]
    return any((it.get("grade") in SHOW and (d in (it.get("refund"), it.get("listing")) or sub(it, d)))
               or (week and not it.get("grade") and sub(it, d)) for it in items for d in days)


def shot(day, week=False):
    """헤드리스 크롬으로 ?card=1 화면을 찍고 배경 여백을 잘라 PNG 경로를 돌려준다."""
    out = os.path.join(tempfile.gettempdir(), f"ipo_{day}.png")
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=2",
                    "--window-size=600,1600", f"--screenshot={out}", f"{URL}?card={'week' if week else 1}&day={day}&t={int(time.time())}"],
                   check=True, capture_output=True, timeout=60)
    img = Image.open(out).convert("RGB")
    bg = Image.new("RGB", img.size, img.getpixel((2, 2)))
    l, t, r, b = ImageChops.difference(img, bg).getbbox()
    pad = 36
    img.crop((max(0, l - pad), max(0, t - pad), min(img.width, r + pad), min(img.height, b + pad))).save(out)
    return out


def clip_set(fmt, data):
    h = k32.GlobalAlloc(0x2, len(data))
    ctypes.memmove(k32.GlobalLock(h), data, len(data))
    k32.GlobalUnlock(h)
    for _ in range(10):  # 다른 앱이 클립보드를 잡고 있으면 잠깐 기다림
        if u32.OpenClipboard(None):
            break
        time.sleep(0.2)
    u32.EmptyClipboard()
    u32.SetClipboardData(fmt, h)
    u32.CloseClipboard()


def clip_image(path):
    buf = io.BytesIO()
    Image.open(path).convert("RGB").save(buf, "BMP")
    clip_set(8, buf.getvalue()[14:])  # CF_DIB = BMP 파일 헤더 14바이트 뺀 것


class GUI(ctypes.Structure):
    _fields_ = [("cbSize", W.DWORD), ("flags", W.DWORD), ("active", W.HWND), ("focus", W.HWND),
                ("capture", W.HWND), ("menu", W.HWND), ("move", W.HWND), ("caret", W.HWND), ("rc", W.RECT)]


def focus(hwnd, target=None):
    """창을 앞으로, 입력칸에 커서. 둘 다 확인되면 True. (Alt 키 꼼수는 다른 창 메뉴를 열어서 안 씀)"""
    cur = k32.GetCurrentThreadId()
    fgt = u32.GetWindowThreadProcessId(u32.GetForegroundWindow(), None)
    kt = u32.GetWindowThreadProcessId(hwnd, None)
    u32.AttachThreadInput(cur, fgt, True); u32.AttachThreadInput(cur, kt, True)
    u32.ShowWindow(hwnd, 9); u32.BringWindowToTop(hwnd); u32.SetForegroundWindow(hwnd)
    if target:
        u32.SetFocus(target)
    u32.AttachThreadInput(cur, kt, False); u32.AttachThreadInput(cur, fgt, False)
    time.sleep(0.7)
    g = GUI(cbSize=ctypes.sizeof(GUI))
    u32.GetGUIThreadInfo(kt, ctypes.byref(g))
    return u32.GetForegroundWindow() == hwnd and (target is None or g.focus == target)


def key(*vks):
    for v in vks:
        u32.keybd_event(v, 0, 0, 0)
    for v in reversed(vks):
        u32.keybd_event(v, 0, 2, 0)
    time.sleep(0.5)


def open_room(name):
    hwnd = u32.FindWindowW(None, name)
    if not hwnd:
        main = u32.FindWindowW(None, "카카오톡")
        if not main or not focus(main):
            sys.exit("카카오톡 메인 창을 앞으로 못 띄움. 키 안 누름")
        # 채팅 탭 클릭 → Ctrl+F 방 이름 검색 → 첫 결과 Enter. 엉뚱한 방이 열려도 아래 제목 확인에서 멈춤
        # (친구 탭 검색엔 나와의 채팅이 안 나오고, Ctrl+2 는 탭 전환 안 됨. 2026-11-13 확인)
        # ponytail: 채팅 탭 아이콘 위치 고정값(창 왼쪽 위 기준, DPI 비인식 좌표). 카톡 화면 바뀌면 다시 잼
        r = W.RECT()
        u32.GetWindowRect(main, ctypes.byref(r))
        u32.SetCursorPos(r.left + 31, r.top + 116)
        u32.mouse_event(2, 0, 0, 0, 0); u32.mouse_event(4, 0, 0, 0, 0)
        time.sleep(1)
        key(0x11, 0x46)
        key(0x24); key(0x10, 0x23)  # Home, Shift+End: 남은 검색어 선택 (Ctrl+A 는 카톡에서 친구 추가라 안 씀)
        clip_set(13, (name + "\0").encode("utf-16-le"))
        key(0x11, 0x56)
        time.sleep(1.2)
        key(0x0D)
        time.sleep(1.5)
        focus(main); key(0x1B)  # 검색어 지우기 (빈 검색칸에서 Esc 는 메인 창을 숨김)
        hwnd = u32.FindWindowW(None, name)
    edit = hwnd and u32.FindWindowExW(hwnd, None, "RICHEDIT50W", None)
    if not edit:
        sys.exit(f"'{name}' 채팅방 창이 없음. 안 보냄")
    return hwnd, edit


def main():
    args = sys.argv[1:]
    opt = lambda k, d: args[args.index(k) + 1] if k in args else d
    to, day = opt("--to", "손정우"), opt("--date", dt.date.today().isoformat())
    week = "--week" in args  # 일요일 다음 주 미리보기 (휴장일 검사 안 함)
    if week and "--shot" not in args:
        sync_open_days()  # 주 1회 휴장일 갱신
    if not week and not is_open(dt.date.fromisoformat(day)):  # 휴장일(주말·공휴일·기타)은 안 보냄
        print(f"{day}: 휴장일, 안 보냄")
        return
    if not has_events(day, week):
        print(f"{day}: 보낼 일정 없음, 안 보냄")
        return
    png = shot(day, week)
    print("사진:", png)
    if "--shot" in args:
        return
    for name in to.split(";"):  # 예: --to "손정우;최미희;어머니, 최미희, 아버지, 대초가"
        hwnd, edit = open_room(name)
        if not focus(hwnd, edit):
            sys.exit(f"'{name}' 입력칸에 커서를 못 놓음. 안 보냄")
        clip_image(png)
        key(0x11, 0x56)  # Ctrl+V: 사진 보내기 확인 창이 뜸
        time.sleep(1.5)
        key(0x0D)  # 확인 창에서 전송
        time.sleep(1.5)
        print(f"{name}: 전송함")


def log(msg):
    with open(os.path.join(HERE, "kakao_send.log"), "a", encoding="utf-8") as f:
        print(f"{dt.datetime.now():%Y-%m-%d %H:%M} {msg}", file=f)


def alert(msg):
    """실패를 나와의 채팅에 한 줄로. 화면이 잠겨 있으면 이것도 못 보냄 (로그에는 남음)."""
    hwnd, edit = open_room(ALERT_TO)
    if not focus(hwnd, edit):
        return
    clip_set(13, (msg + chr(0)).encode("utf-16-le"))
    key(0x11, 0x56)
    key(0x0D)


if __name__ == "__main__":
    try:
        main()
    except BaseException as e:  # sys.exit("이유") 와 예외 모두 실패. 정상 종료(return)는 여기 안 옴
        if isinstance(e, SystemExit) and not isinstance(e.code, str):
            raise
        why = e.code if isinstance(e, SystemExit) else f"{type(e).__name__}: {e}"
        log("실패 " + " ".join(sys.argv[1:]) + " | " + why)
        if "--shot" not in sys.argv:
            try:
                alert(f"[공모주 알림 실패] {why}")
            except BaseException as e2:  # noqa: BLE001 알림 실패는 로그만
                log(f"알림도 실패 | {e2}")
        raise
