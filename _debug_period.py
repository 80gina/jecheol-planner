"""periodProductList 응답을 눈으로 확인하는 임시 진단 스크립트.

prices_raw.csv 의 date 열이 전부 같은 날짜로 찍히는 원인을 찾기 위한 것이다.
분석 파이프라인의 일부가 아니므로 커밋하지 않아도 된다.

실행:  python _debug_period.py
"""
from __future__ import annotations

import json
import logging
from datetime import date, timedelta
from pathlib import Path

import config
import kamis

BASE_DIR = Path(__file__).resolve().parent
OUT = BASE_DIR / "output"

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("debug")


def main() -> int:
    cfg = json.loads((BASE_DIR / "config.json").read_text(encoding="utf-8"))
    key = config.get_key("KAMIS_CERT_KEY")
    cid = config.get_key("KAMIS_CERT_ID")

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=60)

    print()
    print(f"  조회: 배추(211) {start} ~ {end}  소매")
    print()

    payload = kamis.period_price(
        cfg, log, key, cid, start.isoformat(), end.isoformat(),
        category_code="200", item_code="211",
        kind_code="", rank_code="04", country_code="", cls_code="01")

    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / "debug_period_배추.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  원문 저장 → {path}")
    print()

    print("  ── 최상위 구조 ──")
    if isinstance(payload, dict):
        for k, v in payload.items():
            kind = type(v).__name__
            n = f" (len {len(v)})" if isinstance(v, (list, dict)) else ""
            print(f"    {k}: {kind}{n}")
    else:
        print(f"    (문자열 응답) {str(payload)[:300]}")
        return 1

    rows = kamis._rows(payload)
    print()
    print(f"  ── _rows() 가 찾아낸 줄: {len(rows)}개 ──")
    for r in rows[:5]:
        print("   ", json.dumps(r, ensure_ascii=False))
    print()
    if rows:
        print("  ── 첫 줄의 필드 이름 ──")
        print("   ", list(rows[0].keys()))
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
