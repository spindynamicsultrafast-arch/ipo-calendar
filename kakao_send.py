"""오늘 공모주 일정을 카톡 PC 앱으로 보낸다 (창에 직접 글 넣고 Enter. 포커스 안 뺏음).

사용:
  python kakao_send.py --print            # 메시지만 출력
  python kakao_send.py --dry              # 채팅방에 붙여넣기까지만, 전송(Enter) 안 함
  python kakao_send.py                    # 실제 전송
  옵션: --to 방이름 (기본 최미희), --date 2026-11-13

조건: PC 켜짐, 카톡 PC 앱 로그인(잠금 모드 아님). 받는 사람은 친구 목록 이름. 방 이름이 정확히 같은 창이 안 열리면 보내지 않고 멈춘다.
"""
import ctypes
import datetime as dt
import json
import re
import sys
import time
import urllib.request

URL = "https://spindynamicsultrafast-arch.github.io/ipo-calendar/"
SHOW = {"A", "B"}  # 페이지 기본 필터와 같게: C·대기 제외
u32 = ctypes.windll.user32


def message(day):
    html = urllib.request.urlopen(URL, timeout=20).read().decode("utf-8")
    items = json.loads(re.search(r'<script id="ipo-data" type="application/json">(.*?)</script>', html, re.S)
                       .group(1).replace("<\\/", "</"))["items"]
    won = lambda v: f"{int(v):,}원" if v else "-"
    lines = []
    for it in items:
        if it.get("grade") not in SHOW:
            continue
        uw = it.get("underwriter") or ""
        if it.get("sub_start") and it["sub_start"] <= day <= it["sub_end"]:
            p = it.get("price") or it.get("band_high")
            cash = won(p * (it.get("min_shares") or 10) * (it.get("deposit_pct") or 50) / 100) if p else "-"
            last = " (마감일)" if day == it["sub_end"] else ""
            lines.append(f"[청약{last}] {it['name']} ({it['grade']})\n  {uw} · 최소 {cash}")
        if it.get("refund") == day:
            lines.append(f"[환불] {it['name']}\n  {uw}")
        if it.get("listing") == day:
            lines.append(f"[상장] {it['name']} ({it['grade']})\n  공모가 {won(it.get('price'))} · {uw}")
    if not lines:
        return None
    d = dt.date.fromisoformat(day)
    return f"📅 {d.month}/{d.day}({'월화수목금토일'[d.weekday()]}) 공모주 일정\n\n" + "\n\n".join(lines) + f"\n\n{URL}"


WM_SETTEXT, WM_KEYDOWN, WM_KEYUP, VK_RETURN = 0x0C, 0x100, 0x101, 0x0D


def child(parent, cls, title=None, after=None):
    return u32.FindWindowExW(parent, after, cls, title)


def put(edit, text, enter):
    """창을 앞으로 띄우지 않고 입력칸에 직접 글을 넣고 Enter 를 보낸다 (포커스 필요 없음)."""
    u32.SendMessageW(edit, WM_SETTEXT, 0, ctypes.c_wchar_p(text))
    time.sleep(0.3)
    if enter:
        sc = u32.MapVirtualKeyW(VK_RETURN, 0) << 16  # 스캔코드 없으면 카톡이 Enter 로 안 받음
        u32.PostMessageW(edit, WM_KEYDOWN, VK_RETURN, sc | 1)
        time.sleep(0.05)
        u32.PostMessageW(edit, WM_KEYUP, VK_RETURN, sc | 0xC0000001)
        time.sleep(0.8)


def text(edit):
    buf = ctypes.create_unicode_buffer(2000)
    u32.SendMessageW(edit, 0x0D, 2000, buf)  # WM_GETTEXT
    return buf.value


def open_room(name):
    hwnd = u32.FindWindowW(None, name)
    if hwnd:
        return hwnd
    main = u32.FindWindowW(None, "카카오톡")
    view = child(main, "EVA_ChildWindow")
    friends = child(view, "EVA_Window")  # 친구 탭 (ContactListView)
    search = child(friends, "Edit")
    if not search:
        sys.exit("카카오톡 친구 검색칸을 못 찾음 (로그인·실행 확인)")
    put(search, name, enter=True)  # 친구 검색 첫 결과로 1:1 채팅 열기
    time.sleep(1.2)
    put(search, "", enter=False)
    return u32.FindWindowW(None, name)  # 제목이 정확히 같은 창만 인정


def main():
    args = sys.argv[1:]
    opt = lambda k, d: args[args.index(k) + 1] if k in args else d
    to, day = opt("--to", "최미희"), opt("--date", dt.date.today().isoformat())
    msg = message(day)
    if not msg:
        print(f"{day}: 보낼 일정 없음")
        return
    print(msg)
    if "--print" in args:
        return
    hwnd = open_room(to)
    edit = hwnd and child(hwnd, "RICHEDIT50W")
    if not edit:
        sys.exit(f"'{to}' 채팅방 창을 못 열었음. 안 보냄")
    put(edit, msg, enter="--dry" not in args)
    if "--dry" in args:
        print("입력칸에 넣기만 함 (전송 안 함)")
    elif text(edit):
        sys.exit("Enter 가 안 먹힘: 입력칸에 글이 남아 있음. 안 보내졌을 수 있음")
    else:
        print("전송함 (입력칸 비워짐 확인)")


if __name__ == "__main__":
    main()
