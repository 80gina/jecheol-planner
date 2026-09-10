"""제철밥상 플래너 — 지역별 제철 식재료·가격·맞춤 요리 추천 CLI.

    python main.py basket                         # 분석할 장바구니 확인 (키 없어도 됨)
    python main.py probe --date 2026-08-26        # KAMIS 응답 구조 확인 (개발용)
    python main.py codes                          # 품목 코드를 KAMIS 에서 받아 저장
    python main.py collect --years 2              # 기간별 가격 수집 → data/prices_raw.csv
    python main.py weather --years 2              # 기상청 기온·강수 수집
    python main.py analyze                        # 정제·분석·그래프 6장
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
STATE_PATH = BASE_DIR / "data" / "collect_state.json"
WEATHER_CSV = BASE_DIR / "data" / "weather_raw.csv"


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

    pp = sub.add_parser("probe-period",
                        help="기간 조회 응답 구조를 확인한다 (개발용)")
    pp.add_argument("--key", default="baechu",
                    help="장바구니 키 (기본: baechu)")
    pp.add_argument("--days", type=int, default=20,
                    help="최근 며칠치로 시험할지 (기본: 20)")
    pp.add_argument("--cls", default="01", choices=["01", "02"])

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
    co.add_argument("--resume", action="store_true",
                    help="이미 받은 품목은 건너뛰고 이어서 받는다")
    co.add_argument("--cls", default="01", choices=["01", "02"],
                    help="01=소매, 02=도매 (기본: 01)")
    co.add_argument("--country", default="", help="지역 코드 (생략하면 전국)")

    we = sub.add_parser("weather", help="기상청 일별 기온·강수를 수집한다")
    we.add_argument("--years", type=int, default=2, help="몇 년치 (기본: 2)")
    we.add_argument("--region", default="창원", help="관측지점 이름 (기본: 창원)")

    an = sub.add_parser("analyze", help="정제·분석하고 그래프를 그린다")
    an.add_argument("--focus", default="baechu",
                    help="이동평균·분해를 자세히 볼 품목 키 (기본: baechu)")

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
    for it in basket.BASKET:
        print(f"    · {basket.label(it)} — {it['why']}")
    print()
    print("  장바구니에서 뺀 것과 이유")
    for name, why in basket.EXCLUDED:
        print(f"    · {name} — {why}")
    print()
    print(f"  등급은 상품({basket.RANK_CODE})으로 고정합니다. "
          "상품·중품이 섞이면 하루에 값이 두 개가 됩니다.")
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


def cmd_probe_period(args, cfg: dict, log) -> int:
    """기간 조회(periodProductList) 응답이 실제로 어떤 모양인지 확인한다.

    왜 이 명령이 뒤늦게 생겼나
        probe 로 '하루치 조회'의 응답 구조는 확인했으면서,
        '기간 조회'의 응답은 확인하지 않고 필드 이름을 짐작해 파서를 짰다.
        그 결과 날짜가 전부 같은 값으로 들어오는 것을 뒤늦게 발견했다.
        같은 API 라도 액션이 다르면 응답도 다르다 — 액션마다 확인해야 한다.
    """
    import kamis

    if not CODES_PATH.exists():
        print("[ERROR] 먼저 실행하세요:  python main.py codes")
        return 2

    cert_key, cert_id = _keys(log)
    if not cert_key:
        return 2

    meta = json.loads(CODES_PATH.read_text(encoding="utf-8"))
    it = meta.get("items", {}).get(args.key)
    if not it:
        print(f"[ERROR] '{args.key}' 를 item_codes.json 에서 못 찾았습니다.")
        print("  쓸 수 있는 키: " + ", ".join(meta.get("items", {})))
        return 2

    import basket
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=args.days)
    log.info("기간 조회 시험: %s  %s ~ %s", it.get("label"), start, end)

    try:
        payload = kamis._get(cfg, log, kamis._params(
            cfg, cert_key, cert_id,
            action="periodProductList",
            p_productclscode=args.cls,
            p_startday=start.isoformat(),
            p_endday=end.isoformat(),
            p_itemcategorycode=it["category_code"],
            p_itemcode=it["item_code"],
            p_productrankcode=basket.RANK_CODE,
            p_convert_kg_yn="N",
        ))
    except kamis.KamisError as e:
        log.error("조회 실패: %s", e)
        return 3

    out = BASE_DIR / "output"
    path = kamis.save_raw(payload, out, f"period_{args.key}_{start}_{end}", log)

    print()
    print("=" * 66)
    print(f"  기간 조회 응답 구조 — {it.get('label')} ({start} ~ {end})")
    print("=" * 66)
    for line in kamis.summarize_shape(payload)[:70]:
        print("  " + line)

    rows = kamis._rows(payload)
    print()
    print(f"  파서가 찾은 행: {len(rows)}개")
    if rows:
        print("  첫 행의 모든 필드:")
        for k, v in rows[0].items():
            print(f"    {k:<20} = {str(v)[:50]}")
        if len(rows) > 1:
            print("  둘째 행:")
            for k, v in rows[1].items():
                print(f"    {k:<20} = {str(v)[:50]}")
        print()
        print(f"  현재 파서가 뽑아낸 날짜: {_row_date(rows[0])} / {_row_date(rows[-1])}")
        print(f"  현재 파서가 뽑아낸 가격: {_row_price(rows[0])} / {_row_price(rows[-1])}")
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

            # 1) 품목명이 정확히 같은 행만 남긴다 ('파' 로 '쪽파'가 걸리지 않게)
            cand = [i for i in items if i["item_name"] == want["item"]]
            # 2) 등급을 상품(04)으로 좁힌다. 섞이면 하루에 값이 두 개가 된다
            r04 = [i for i in cand if i["rank_code"] == basket.RANK_CODE]
            cand = r04 or cand
            # 3) 품종을 지정했으면 그 말이 든 품종만
            if want["kind"]:
                k = [i for i in cand if want["kind"] in i["kind_name"]]
                if not k:
                    log.warning("  %s — 품종 '%s' 를 못 찾았습니다. 있는 품종: %s",
                                want["item"], want["kind"],
                                ", ".join(sorted({c["kind_name"] for c in cand})) or "(없음)")
                cand = k or cand

            if cand:
                hit = cand[0]
                found[want["key"]] = {
                    **hit,
                    "key": want["key"],
                    "category": cat,
                    "category_code": cat_code,
                    "role": want["role"],
                    # 품종을 지정한 품목만 조회 때 품종을 고정한다.
                    # 배추·무처럼 계절마다 품종이 바뀌는 것은 비워 둔다 (basket.py 참조)
                    "pin_kind": bool(want["kind"]),
                    "label": basket.label(want),
                }
        time.sleep(cfg.get("request", {}).get("delay_sec", 0.7))

    for want in basket.BASKET:
        if want["key"] not in found:
            unmatched.append(f"{basket.label(want)} ({want['category']})")

    CODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    CODES_PATH.write_text(
        json.dumps({"regday": regday, "items": found}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    print()
    print("=" * 62)
    print("  품목 코드 확인 결과")
    print("=" * 62)
    for key, it in found.items():
        pin = "품종 고정" if it["pin_kind"] else "품목 전체"
        print(f"  {it['label']:<7} 품목 {it['item_name']}({it['item_code']:>3}) "
              f"· 품종 {it['kind_name'] or '-'}({it['kind_code'] or '-'}) "
              f"· {it['rank_name'] or '-'} · {it['unit'] or '-'}  [{pin}]")
    if unmatched:
        print()
        print("  ⚠ 못 찾은 품목: " + ", ".join(unmatched))
        print("     basket.py 의 item / kind 를 KAMIS 가 쓰는 이름으로 고치세요.")
    print()
    print(f"  저장: {CODES_PATH}")
    print()
    return 0


# ─────────────────────────────────────── collect

def cmd_collect(args, cfg: dict, log) -> int:
    """장바구니 품목의 기간별 가격을 모아 하나의 CSV 로 만든다."""
    import basket
    import kamis

    basket_rank = basket.RANK_CODE

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

    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365 * args.years)
    # 60일씩 자른다.
    #   probe-period 로 20일 = 735행이 몇 초 만에 왔다. 3개월은 시간 초과가 났다.
    #   그 사이 어디쯤이 한계이므로 60일에서 시작하고, 안 되면 fetch() 가 쪼갠다.
    chunks = kamis.day_chunks(start.isoformat(), end.isoformat(), 60)

    # 중간에 멈춰도 받은 데이터는 남긴다.
    #
    # 이어받기에서 '받았다'의 기준
    #   CSV 에 행이 있다고 다 받은 것이 아니다. 중단된 품목도 절반쯤 들어 있다.
    #   그것까지 건너뛰면 반토막 데이터로 분석하게 된다 (실제로 겪은 버그다).
    #   그래서 품목을 **끝까지 마쳤을 때만** collect_state.json 에 적고,
    #   이어받기는 그 목록만 믿는다.
    rows: list[dict] = []
    done: set[str] = set()
    if args.resume and RAW_CSV.exists() and STATE_PATH.exists():
        done = set(json.loads(STATE_PATH.read_text(encoding="utf-8")).get("done", []))
        with open(RAW_CSV, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                if r["key"] not in done:
                    continue                    # 절반만 받은 품목은 버리고 다시 받는다
                r["price"] = int(r["price"])
                rows.append(r)
        log.info("이어받기: 완료된 품목 %d개 (%d행) 건너뜁니다", len(done), len(rows))
    elif args.resume:
        log.info("이어받기: 이전 기록이 없어 처음부터 받습니다")

    todo = [(k, v) for k, v in items.items() if k not in done]
    total_calls = len(todo) * len(chunks)
    print()
    print(f"  수집 기간  {start} ~ {end}")
    print(f"  조회 횟수  품목 {len(todo)}개 × 구간 {len(chunks)}개 = {total_calls}회")
    print(f"  예상 시간  약 {total_calls * 3 // 60}~{total_calls * 6 // 60 + 1}분")
    print(f"  중간에 멈춰도 받은 만큼은 저장됩니다. 다시 할 때 --resume 을 붙이세요.")
    print()

    delay = cfg.get("request", {}).get("delay_sec", 0.7)
    calls = 0
    t0 = time.time()

    # 서버가 한 번에 돌려주는 한계를 모르므로, 통한 크기를 기억해 다음부터 그 크기로 묻는다.
    learned = {"span": None}      # 성공한 구간의 일수 중 가장 큰 값

    def fetch(it: dict, s: str, e: str, depth: int) -> list[dict]:
        """한 구간을 받아온다. 빈 응답이면 절반으로 쪼개 다시 물어본다.

        KAMIS 기간 조회는 한 번에 돌려줄 양에 한계가 있는데 그 값이 공개돼 있지 않다.
        넘으면 오류가 아니라 **빈 응답**이 와서 조용히 지나간다 —
        실제로 1년 구간을 요청했다가 하루치만 모은 적이 있다.
        그래서 한계를 짐작하지 않고, 비면 쪼갠다.
        """
        nonlocal calls
        try:
            data = kamis.period_price(
                cfg, log, cert_key, cert_id, s, e,
                it["category_code"], it["item_code"],
                kind_code=it["kind_code"] if it.get("pin_kind") else "",
                rank_code=basket_rank,
                country_code=args.country, cls_code=args.cls)
        except kamis.KamisError as err:
            print(f"      ⚠ {s}~{e} 실패 — {str(err)[:60]}")
            data = []
        calls += 1
        time.sleep(delay)

        if data:
            span = (date.fromisoformat(e) - date.fromisoformat(s)).days
            if learned["span"] is None or span > learned["span"]:
                learned["span"] = span
            return data
        halves = kamis.split_range(s, e)
        if not halves or depth >= 5:
            return []
        span = (date.fromisoformat(e) - date.fromisoformat(s)).days
        print(f"      ↳ {span}일 구간이 안 되어 절반으로 나눠 다시 받습니다")
        out: list[dict] = []
        for hs, he in halves:
            out += fetch(it, hs, he, depth + 1)
        return out

    def save(mark: str | None = None) -> int:
        """CSV 를 다시 쓰고, 품목을 마쳤으면 완료 목록에 적는다."""
        if mark:
            done.add(mark)
            STATE_PATH.write_text(
                json.dumps({"done": sorted(done),
                            "기간": [str(start), str(end)]}, ensure_ascii=False, indent=2),
                encoding="utf-8")
        rows.sort(key=lambda r: (r["key"], r["date"]))
        RAW_CSV.parent.mkdir(parents=True, exist_ok=True)
        with open(RAW_CSV, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["date", "key", "item", "kind",
                                              "category", "role", "price"])
            w.writeheader()
            w.writerows(rows)
        return len(rows)

    try:
        for n, (key, it) in enumerate(todo, 1):
            name = it.get("label") or it["item_name"]
            got = 0
            how = "-"
            for c, (s, e) in enumerate(chunks, 1):
                elapsed = time.time() - t0
                eta = (elapsed / calls) * max(total_calls - calls, 0) if calls else 0
                print(f"  [{n}/{len(todo)}] {name:<6} 구간 {c}/{len(chunks)}  "
                      f"{s[:7]}~{e[:7]}  ·  누적 {len(rows) + got:,}행  "
                      f"·  남은 시간 약 {int(eta // 60)}분 {int(eta % 60):02d}초",
                      flush=True)
                data = fetch(it, s, e, depth=0)
                if not data:
                    print(f"      ⚠ {s}~{e} 구간에서 한 행도 못 받았습니다")
                    continue
                data, how = _pick_average(data)
                for r in data:
                    d = _row_date(r)
                    p = _row_price(r)
                    if not d or p is None:
                        continue
                    rows.append({
                        "date": d, "key": key,
                        "item": name,
                        "kind": r.get("kindname") or it.get("kind_name") or "",
                        "category": it["category"], "role": it["role"],
                        "price": p,
                    })
                    got += 1
                time.sleep(delay)
            print(f"      → {name} {got}행 완료 (지역: {how if got else '-'})")
            save(mark=key)  # 품목 하나를 끝까지 마쳤을 때만 완료로 적는다

            # 첫 품목에서 배운 구간 크기로 나머지를 다시 나눈다.
            # 쪼개기를 되풀이하지 않아 호출 수가 크게 준다.
            if n <= 2 and learned["span"] and learned["span"] < 55:
                new_chunks = kamis.day_chunks(start.isoformat(), end.isoformat(),
                                              learned["span"])
                if len(new_chunks) != len(chunks):
                    print(f"      ℹ {learned['span']}일 구간이 통하는 것을 확인했습니다. "
                          f"남은 품목은 {len(new_chunks)}구간으로 나눠 받습니다")
                    chunks = new_chunks
                    total_calls = len(todo) * len(chunks)
    except KeyboardInterrupt:
        n_saved = save()
        print()
        print("  ⏹ 중단했습니다. 여기까지 받은 것은 저장돼 있습니다.")
        print(f"     {n_saved:,}행 → {RAW_CSV}")
        print("     이어서 받으려면:  python main.py collect --years 2 --resume")
        print()
        return 130

    if not rows:
        print("[ERROR] 한 행도 못 받았습니다. probe 로 응답을 먼저 확인하세요.")
        return 3

    save()

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


def _pick_average(rows: list[dict]) -> tuple[list[dict], str]:
    """지역·시장별로 쪼개져 오는 행 중 '전국 평균'만 고른다.

    기간 조회 응답은 같은 날짜에 대해 지역(countyname)과 시장(marketname)별로
    행을 여러 개 준다. 20일 조회에 735행이 온 이유가 이것이다.
    그대로 쓰면 같은 날에 값이 수십 개가 되어 시계열이 성립하지 않는다.

    countyname 이 '평균'인 행이 전국 평균이다. 그것만 남긴다.
    지역코드를 지정해 받은 경우에는 '평균'이 없을 수 있으므로,
    없으면 전부 남기고 뒤(analyze)에서 날짜별 중앙값으로 합친다.
    """
    avg = [r for r in rows if str(r.get("countyname") or "").strip() == "평균"]
    if avg:
        return avg, "평균"
    return rows, "전체(평균 없음)"


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


# ─────────────────────────────────────── weather

def cmd_weather(args, cfg: dict, log) -> int:
    """기상청 일자료를 받아 CSV 로 저장한다. KAMIS 와 독립이라 먼저 해도 된다."""
    import weather

    station = weather.STATIONS.get(args.region)
    if not station:
        print(f"[ERROR] 모르는 지역입니다: {args.region}")
        print("  쓸 수 있는 지역: " + ", ".join(weather.STATIONS))
        return 2

    try:
        key = config.get_key("KMA_SERVICE_KEY")
    except config.ConfigError as e:
        log.error("%s", e)
        print()
        print("  공공데이터포털(data.go.kr)에서 '기상청_지상(종관, ASOS) 일자료'를")
        print("  활용신청하면 대개 바로 발급됩니다. 일반 인증키(Decoding) 를 넣으세요.")
        print()
        return 2

    # 기상청 ASOS 일자료는 하루가 끝나야 확정된다. 오늘 것을 달라고 하면
    # 자료가 없어서가 아니라 "날짜 범위가 잘못됐다"며 전체를 거절한다.
    # 그래서 끝 날짜를 어제로 잡는다.
    end = date.today() - timedelta(days=1)
    start = end - timedelta(days=365 * args.years)
    log.info("기상 자료 수집 %s ~ %s (%s) — 오늘 자료는 아직 확정 전이라 어제까지",
             start, end, args.region)

    try:
        rows = weather.daily(cfg, log, key, station,
                             start.isoformat(), end.isoformat())
    except weather.WeatherError as e:
        log.error("수집 실패: %s", e)
        return 3

    recs = weather.to_records(rows, args.region)
    if not recs:
        print("[ERROR] 한 행도 못 받았습니다. 인증키와 기간을 확인하세요.")
        return 3

    recs.sort(key=lambda r: r["date"])
    WEATHER_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(WEATHER_CSV, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "region", "avg_ta",
                                          "min_ta", "max_ta", "sum_rn"])
        w.writeheader()
        w.writerows(recs)

    temps = [r["avg_ta"] for r in recs if r["avg_ta"] is not None]
    print()
    print("=" * 62)
    print("  기상 자료 수집 완료")
    print("=" * 62)
    print(f"  지역   {args.region} (관측지점 {station})")
    print(f"  기간   {recs[0]['date']} ~ {recs[-1]['date']}")
    print(f"  행수   {len(recs):,}행")
    if temps:
        print(f"  평균기온  최저 {min(temps):.1f}℃ · 최고 {max(temps):.1f}℃ "
              f"· 평균 {sum(temps)/len(temps):.1f}℃")
    print()
    print(f"  저장: {WEATHER_CSV}")
    print()
    return 0


# ─────────────────────────────────────── analyze

def cmd_analyze(args, cfg: dict, log) -> int:
    import analyze
    return analyze.run(log, focus=args.focus)


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
                "codes": cmd_codes, "collect": cmd_collect,
                "analyze": cmd_analyze, "weather": cmd_weather,
                "probe-period": cmd_probe_period}
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
