"""카톡 알림 로직 (Windows 전용, CI 에선 안 돎: kakao_send 가 PIL·windll 을 씀). python tests/test_kakao.py"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# 카톡 시각 나누기: 상장일 07:30, 청약·환불·정산 08:45 (상장 있는 날은 07:30 사진에 다 들어가 08:45 사진 안 감)
import kakao_send  # noqa: E402
_o, kakao_send.is_open = kakao_send.is_open, lambda d: d.weekday() < 5
_it = [{"grade": "A", "sub_start": "2026-12-01", "sub_end": "2026-12-02", "refund": "2026-12-04", "listing": "2026-12-10"},
       {"grade": "C", "sub_start": "2026-12-14", "sub_end": "2026-12-15", "refund": "2026-12-17", "listing": "2026-12-21"}]
_h = lambda d, at9: kakao_send.has_events(d, False, at9, _it)
assert kakao_send.settle("2026-12-10") == "2026-12-14" and kakao_send.settle("2026-12-11") == "2026-12-15"
assert _h("2026-12-10", False) and not _h("2026-12-10", True)
for _d in ("2026-12-01", "2026-12-04", "2026-12-14"):
    assert _h(_d, True) and not _h(_d, False), _d
assert not _h("2026-12-15", True) and not _h("2026-12-21", False)
_it.append({"grade": "B", "sub_start": "2026-12-10", "sub_end": "2026-12-11", "listing": None, "refund": None})
assert _h("2026-12-10", False) and not _h("2026-12-10", True)
kakao_send.is_open = _o
print("kakao schedule ok")
