"""제철밥상 플래너 — 지역별 제철 식재료·가격·맞춤 요리 추천 CLI.

    python main.py basket                         # 분석할 장바구니 확인 (키 없어도 됨)
    python main.py probe --date 2026-08-26        # KAMIS 응답 구조 확인 (개발용)
    python main.py codes                          # 품목 코드를 KAMIS 에서 받아 저장
    python main.py collect --years 2              # 기간별 가격 수집 → data/prices_raw.csv
    python main.py ingredient                     # 뉴스에서 제철 식재료·지역 추출
    python main.py price --category 채소류         # 지역별 가격 수집
    python main.py menu --people 12               # 지역 맞춤 요리 추천
    python main.py plan --sessions 4              # 요리교실 식단표 + 장보기 목록
    python main.py dashboard                      # HTML 대시보드
    python main.py card --menu "전어무침"          # 순자 할머니 레시피 카드
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import config

BASE_DIR = Path(__file__).resolve().parent
CODES_PATH = BASE_DIR / "data" / "item_codes.json"
RAW_CSV = BASE_DIR / "data" / "prices_raw.csv"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="제철밥상 플래너 — 지역별 제철 식재료·가격·맞춤 요리 추천",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = p.add_subparsers(dest="command", metavar="<명령>")

    sub.add_parser("basket", help="분석할 장바구니를 보여준다 (인증키 없이 동작)")

    pr = sub.add_parser("probe", help="KAMIS 응답 구조를 확인한다 (개발용)")
    pr.add_argument("--date", default=date.today().isoformat(),
                    help="조회 날짜 YYYY-MM-DD (기본: 오늘)")
    pr.add_argument("--category", default="채소류",
                    choices=["식량작물", "채소류", "특용작물", "과일류", "축산물", "수산물"])
    pr.add_argument("--cls", default="01", choices=["01", "02"],
                    help="01=소매, 02=도매 (기본: 01)")
    pr.add_argument("--country", default="", help="지역 코드 (생략 가능)")

    cd = sub.add_parser("codes", help="장바구니 품목의 KAMIS 코드를 받아 저장한다")
    cd.add_argument("--date", default="", help="기준 날짜 (기본: 최근 평일)")

    co = sub.add_parser("collect", help="기간별 가격을 모아 CSV 로 저장한다")
    co.add_argument("--years", type=int, default=2, help="몇 년치 (기본: 2)")
    co.add_argument("--cls", default="01", choices=["01", "02"],
                    help="01=소매, 02=도매 (기본: 01)")
    co.add_argument("--country", default="", help="지역 코드 (생략하면 전국)")

    sub.add_parser("ingredient", help="뉴스에서 제철 식재료·지역을 뽑는다")
    sub.add_parser("price", help="지역별 식재료 가격을 수집한다")
    sub.add_parser("menu", help="지역 맞춤 요리를 추천한다")
    sub.add_parser("plan", help="요리교실 식단표·장보기 목록을 만든다")
    sub.add_parser("dashboard", help="HTML 대시보드를 만든다")
    sub.add_parser("card", help="순자 할머니 레시피 카드를 만든다")

    return p


def _keys(log):
    """인증키를 읽는다. 없으면 (None, None) 을 돌려주고 호출자가 안내한다."""
    try:
        return config.get_key("KAMIS_CERT_KEY"), config.get_key("KAMIS_CERT_ID")
    except config.ConfigError as e:
        log.error("%s", e)
        return None, None


def _recent_weekday() -> str:
    """KAMIS 는 주말·공휴일 시세가 비어 있다. 최근 평일을 기준으로 잡는다."""
    d = date.today() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d.isoformat()


# ─────────────────────────────────────── basket

def cmd_basket(args, cfg, log) -> int:
    import basket

    print()
    print("=" * 62)
    print("  요리교실 장바구니 — 시계열 분석 대상")
    print("=" * 62)
    for line in basket.summary_lines():
        print("  " + line)
    print()
    print(f"  총 {len(basket.BASKET)}개 품목 / 부류 {', '.join(basket.categories_used())}")
    print()
    print("  왜 이 품목들인가")
    for item in basket.BASKET:
        print(f"    · {item['name'][0]} — {item['why']}")
    print()
    return 0


# ─────────────────────────────────────── probe

def cmd_probe(args, cfg: dict, log) -> int:
    """KAMIS 키가 통하는지, 응답이 어떤 모양인지 눈으로 확인한다."""
    import kamis

    cert_key, cert_id = _keys(log)
    if not cert_key:
        return 2

    log.info("KAMIS 인증키: %s / 아이디: %s",
             config.mask(cert_key), config.mask(cert_id))

    try:
        payload = kamis.probe(cfg, log, cert_key, cert_id,
                              args.date, args.category, args.country, args.cls)
    except kamis.KamisError as e:
        log.error("조회 실패: %s", e)
        return 3

    out = BASE_DIR / "output"
    path = kamis.save_raw(payload, out, f"probe_{args.date}_{args.category}", log)

    print()
    print("=" * 62)
    print("  KAMIS 응답 구조")
    print("=" * 62)
    for line in kamis.summarize_shape(payload)[:60]:
        print("  " + line)
    print()
    print(f"  전체 원문: {path}")
    print()
    return 0


# ─────────────────────────────────────── codes

def cmd_codes(args, cfg: dict, log) -> int:
    """장바구니 품목이 KAMIS 에서 어떤 코드로 불리는지 받아 적는다."""
    import basket
    import kamis

    cert_key, cert_id = _keys(log)
    if not cert_key:
        return 2

    regday = args.date or _recent_weekday()
    log.info("기준 날짜: %s", regday)

    found: dict[str, dict] = {}
    unmatched: list[str] = []

    for cat in basket.categories_used():
        cat_code = basket.CATEGORY_CODES[cat]
        log.info("부류 조회: %s (%s)", cat, cat_code)
        try:
            items = kamis.list_items(cfg, log, cert_key, cert_id, regday, cat_code)
        except kamis.KamisError as e:
            log.error("  실패: %s", e)
            continue
        log.info("  품목 %d개 확인", len(items))

        for want in basket.BASKET:
            if want["category"] != cat or want["key"] in found:
                continue
            hit = None
            for alias in want["name"]:                    # 정확히 같은 이름 먼저
                hit = next((i for i in items if i["item_name"] == alias), None)
                if hit:
                    break
            if not hit:                                    # 없으면 포함 관계로
                for alias in want["name"]:
                    hit = next((i for i in items if alias in i["item_name"]), None)
                    if hit:
                        break
            if hit:
                found[want["key"]] = {
                    **hit,
                    "key": want["key"],
                    "category": cat,
                    "category_code": cat_code,
                    "role": want["role"],
                }
        time.sleep(cfg.get("request", {}).get("delay_sec", 0.7))

    for want in basket.BASKET:
        if want["key"] not in found:
            unmatched.append(want["name"][0])

    CODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODES_PATH.write_text(
        json.dumps({"regday": regday, "items": found}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print()
    print("=" * 62)
    print("  품목 코드 확인 결과")
    print("=" * 62)
    for key, it in found.items():
        print(f"  {it['item_name']:<8} 품목코드 {it['item_code']:<6} "
              f"품종 {it['kind_name'] or '-'} ({it['kind_code'] or '-'})")
    if unmatched:
        print()
        print("  ⚠ 못 찾은 품목: " + ", ".join(unmatched))
        print("     basket.py 의 name 목록에 KAMIS 가 쓰는 이름을 추가하세요.")
    print()
    print(f"  저장: {CODES_PATH}")
    print()
    return 0


# ─────────────────────────────────────── collect

def cmd_collect(args, cfg: dict, log) -> int:
    """장바구니 품목의 기간별 가격을 모아 하나의 CSV 로 만든다."""
    import kamis

    if not CODES_PATH.exists():
        print("[ERROR] 품목 코드가 없습니다. 먼저 실행하세요:  python main.py codes")
        return 2

    cert_key, cert_id = _keys(log)
    if not cert_key:
        return 2

    meta = json.loads(CODES_PATH.read_text(encoding="utf-8"))
    items = meta.get("items", {})
    if not items:
        print("[ERROR] item_codes.json 이 비어 있습니다. codes 를 다시 실행하세요.")
        return 2

    end = date.today()
    start = end - timedelta(days=365 * args.years)
    chunks = kamis.month_chunks(start.isoformat(), end.isoformat(), months=6)
    log.info("수집 기간 %s ~ %s (%d구간 × 품목 %d개)",
             start, end, len(chunks), len(items))

    rows: list[dict] = []
    delay = cfg.get("request", {}).get("delay_sec", 0.7)

    for key, it in items.items():
        log.info("[%s] %s", key, it["item_name"])
        got = 0
        for s, e in chunks:
            try:
                data = kamis.period_price(
                    cfg, log, cert_key, cert_id, s, e,
                    it["category_code"], it["item_code"],
                    kind_code=it.get("kind_code", ""),
                    country_code=args.country, cls_code=args.cls)
            except kamis.KamisError as err:
                log.warning("  구간 실패 (%s~%s): %s", s, e, err)
                continue
            for r in data:
                d = _row_date(r)
                p = _row_price(r)
                if not d or p is None:
                    continue
                rows.append({
                    "date": d, "key": key, "item": it["item_name"],
                    "kind": r.get("kindname") or it.get("kind_name") or "",
                    "category": it["category"], "role": it["role"],
                    "price": p,
                })
                got += 1
            time.sleep(delay)
        log.info("  %d행 수집", got)

    if not rows:
        print("[ERROR] 한 행도 못 받았습니다. probe 로 응답을 먼저 확인하세요.")
        return 3

    rows.sort(key=lambda r: (r["key"], r["date"]))
    RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(RAW_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "key", "item", "kind",
                                          "category", "role", "price"])
        w.writeheader()
        w.writerows(rows)

    print()
    print("=" * 62)
    print("  수집 완료")
    print("=" * 62)
    per: dict[str, int] = {}
    for r in rows:
        per[r["item"]] = per.get(r["item"], 0) + 1
    for name, n in per.items():
        flag = "✅" if n >= 100 else "⚠ 100개 미만"
        print(f"  {name:<8} {n:>5}행  {flag}")
    print()
    print(f"  전체 {len(rows)}행 → {RAW_CSV}")
    print()
    return 0


def _row_date(r: dict) -> str | None:
    """응답의 날짜 필드를 YYYY-MM-DD 로 맞춘다.

    periodProductList 는 연도(yyyy)와 월일(regday, "09/06")을 따로 준다.
    """
    y = str(r.get("yyyy") or "").strip()
    md = str(r.get("regday") or "").strip()
    if y and md and "/" in md:
        mm, dd = md.split("/")[:2]
        return f"{y}-{int(mm):02d}-{int(dd):02d}"
    for k in ("regday", "date", "REGDAY"):
        v = str(r.get(k) or "").strip()
        if len(v) == 10 and v[4] in "-/":
            return v.replace("/", "-")
    return None


def _row_price(r: dict) -> int | None:
    """'4,320' 같은 문자열을 숫자로. 결측 표시('-', '', None)는 버린다."""
    v = r.get("price")
    if v is None:
        return None
    s = str(v).replace(",", "").strip()
    if not s or s in ("-", "0"):
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


# ─────────────────────────────────────── 나머지

def not_ready(name: str, stage: str) -> int:
    print(f"[INFO] '{name}' 명령은 아직 준비 중입니다. ({stage})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 0

    try:
        cfg = config.load_config()
    except config.ConfigError as e:
        print(f"[ERROR] {e}")
        return 2

    log = config.setup_logging(cfg, args.log_level)
    log.info("%s — %s", cfg.get("project_name"), args.command)

    handlers = {"basket": cmd_basket, "probe": cmd_probe,
                "codes": cmd_codes, "collect": cmd_collect}
    if args.command in handlers:
        return handlers[args.command](args, cfg, log)

    stages = {
        "ingredient": "2단계에서 추가",
        "price": "3단계에서 추가",
        "menu": "4단계에서 추가",
        "plan": "5단계에서 추가",
        "dashboard": "6단계에서 추가",
        "card": "6단계에서 추가",
    }
    return not_ready(args.command, stages[args.command])


if __name__ == "__main__":
    sys.exit(main())
