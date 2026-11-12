"""오늘·내일 공모주 일정을 사진으로 찍어 카톡 PC 앱 채팅방에 보낸다.

사용:
  python kakao_send.py --shot             # 사진만 만들고 경로 출력 (안 보냄)
  python kakao_send.py                    # 사진 + 링크 전송
  옵션: --to 방이름 (기본 손정우 = 나와의 채팅), --date 2026-11-16

조건: PC 켜짐·잠금 해제, 카톡 PC 앱 로그인. 방 창이 없으면 메인 창에서 Enter(맨 위 내 프로필) 로
나와의 채팅을 연다. 다른 방은 미리 열어 둬야 한다. 창·입력칸 포커스를 확인 못 하면 키를 안 누른다.
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
u32, k32 = ctypes.windll.user32, ctypes.windll.kernel32
k32.GlobalAlloc.restype = k32.GlobalLock.restype = ctypes.c_void_p
k32.GlobalLock.argtypes = k32.GlobalUnlock.argtypes = [ctypes.c_void_p]
u32.SetClipboardData.argtypes = [W.UINT, ctypes.c_void_p]


def has_events(day):
    """오늘·내일 A/B 등급 일정이 있나 (없으면 안 보냄)."""
    html = urllib.request.urlopen(URL, timeout=20).read().decode("utf-8")
    items = json.loads(re.search(r'<script id="ipo-data" type="application/json">(.*?)</script>', html, re.S)
                       .group(1).replace("<\\/", "</"))["items"]
    d0 = dt.date.fromisoformat(day)
    days = {d0.isoformat(), (d0 + dt.timedelta(days=1)).isoformat()}
    return any(it.get("grade") in SHOW and (
        {it.get("refund"), it.get("listing")} & days
        or any(it.get("sub_start") and it["sub_start"] <= x <= it["sub_end"] for x in days)) for it in items)


def shot(day):
    """헤드리스 크롬으로 ?card=1 화면을 찍고 배경 여백을 잘라 PNG 경로를 돌려준다."""
    out = os.path.join(tempfile.gettempdir(), f"ipo_{day}.png")
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", "--force-device-scale-factor=2",
                    "--window-size=600,1600", f"--screenshot={out}", f"{URL}?card=1&day={day}"],
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


def clip_text(s):
    clip_set(13, (s + "\0").encode("utf-16-le"))  # CF_UNICODETEXT (powershell 경유는 한글 깨짐)


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
        key(0x0D)  # 친구 목록 맨 위(내 프로필)에서 Enter = 나와의 채팅
        time.sleep(1.5)
        hwnd = u32.FindWindowW(None, name)
    edit = hwnd and u32.FindWindowExW(hwnd, None, "RICHEDIT50W", None)
    if not edit:
        sys.exit(f"'{name}' 채팅방 창이 없음. 안 보냄")
    return hwnd, edit


def main():
    args = sys.argv[1:]
    opt = lambda k, d: args[args.index(k) + 1] if k in args else d
    to, day = opt("--to", "손정우"), opt("--date", dt.date.today().isoformat())
    if not has_events(day):
        print(f"{day}: 오늘·내일 보낼 일정 없음")
        return
    png = shot(day)
    print("사진:", png)
    if "--shot" in args:
        return
    hwnd, edit = open_room(to)
    if not focus(hwnd, edit):
        sys.exit(f"'{to}' 입력칸에 커서를 못 놓음. 안 보냄")
    clip_image(png)
    key(0x11, 0x56)  # Ctrl+V: 사진 보내기 확인 창이 뜸
    time.sleep(1.5)
    key(0x0D)  # 확인 창에서 전송
    time.sleep(1.5)
    if focus(hwnd, edit):
        clip_text(URL)
        key(0x11, 0x56); key(0x0D)
    print("전송함 (카톡에서 확인)")


if __name__ == "__main__":
    main()
