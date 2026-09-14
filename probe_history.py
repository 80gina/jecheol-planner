"""KAMIS 기간 조회가 과거 몇 년까지 답해 주는지 확인하는 일회성 진단 스크립트.

배경:
    collect 는 2년치(2024-09 ~ 2026-09)를 요청했는데 실제로 받은 자료는
    2025-09-10 부터였다. KAMIS 가 최근 1년만 제공하는지, 아니면 수집 쪽
    문제인지를 가르기 위해 '옛 구간만' 콕 집어 물어본다.

    probe-period 는 오늘부터 거꾸로 N일만 보므로 이 확인에는 쓸 수 없다.

실행:  python probe_history.py

분석 파이프라인의 일부가 아니다. 확인이 끝나면 지워도 된다.
"""
from __future__ import annotations

import json
import logging
from datetime import date
from pathlib import Path

import config
import kamis

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(level=logging.WARNING, format="[%(levelname)s] %(message)s")
log = logging.getLogger("probe")

# 배추 한 품목으로만 확인한다. 한 품목에서 안 나오면 다른 품목도 마찬가지다.
CATEGORY, ITEM, RANK = "200", "211", "04"

# 오늘로부터 거슬러 올라가며 3개월짜리 창을 하나씩 물어본다.
WINDOWS = [
    ("2026-06-01", "2026-08-31", "3개월 전"),
    ("2026-01-01", "2026-03-31", "8개월 전"),
    ("2025-09-15", "2025-12-15", "1년 전 직후"),
    ("2025-06-01", "2025-08-31", "1년 3개월 전"),
    ("2025-01-01", "2025-03-31", "1년 8개월 전"),
    ("2024-10-01", "2024-12-31", "2년 전"),
    ("2024-01-01", "2024-03-31", "2년 8개월 전"),
]


def main() -> int:
    cfg = json.loads((BASE_DIR / "config.json").read_text(encoding="utf-8"))
    key = config.get_key("KAMIS_CERT_KEY")
    cid = config.get_key("KAMIS_CERT_ID")

    print()
    print(f"  KAMIS 과거 제공 범위 확인 — 배추(코드 {ITEM}) 소매, 오늘 {date.today()}")
    print()
    print(f"  {'구간':<26}{'설명':<14}{'받은 줄':>8}   {'실제 날짜 범위':<26}")
    print("  " + "-" * 78)

    first_ok = None
    for start, end, note in WINDOWS:
        try:
            payload = kamis.period_price(
                cfg, log, key, cid, start, end,
                category_code=CATEGORY, item_code=ITEM,
                kind_code="", rank_code=RANK, country_code="", cls_code="01")
        except Exception as exc:                      # noqa: BLE001
            print(f"  {start}~{end:<12} {note:<14}{'예외':>8}   {type(exc).__name__}: {exc}")
            continue

        err = kamis.error_message(payload)
        rows = kamis._rows(payload)

        if err:
            shown = f"오류: {err}"
        elif not rows:
            shown = "빈 응답 (제공 범위 밖으로 보임)"
        else:
            days = sorted({r.get("regday") or r.get("yyyy") or "" for r in rows})
            days = [d for d in days if d]
            shown = f"{days[0]} ~ {days[-1]}" if days else "(날짜 필드 없음)"
            if first_ok is None:
                first_ok = (start, end)

        print(f"  {start}~{end:<12} {note:<14}{len(rows):>8}   {shown}")

    print()
    print("  판단 기준")
    print("    · 최근 구간은 줄이 오고 옛 구간부터 0 이면 → KAMIS 가 제공 범위를 제한하는 것")
    print("    · 옛 구간도 줄이 오면 → 수집 로직 쪽 문제이므로 다시 받아야 함")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
