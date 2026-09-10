"""price — 수집한 시계열에서 '지금 시세'를 뽑아 요리교실 앱이 읽는 형식으로 내보낸다.

무엇을 하나
    data/prices_raw.csv (collect 가 만든 원자료) 를 읽어
    품목별로 ① 최근 값 ② 전주 대비 ③ 전년 동기 대비 를 계산하고,
    제철밥상 요리교실 앱의 구글시트 `05_시세` 형식(13열)으로 내보낸다.

왜 '평년'이 아니라 '전년 동기'인가
    평년은 보통 5년 평균을 뜻한다. 지금 수집한 기간은 2년이라 5년 평균을 낼 수 없다.
    없는 값을 평년이라 부르면 리포트가 틀린 말을 하게 되므로,
    실제로 계산 가능한 '전년 동기 대비'로 적고 그 사실을 출처에 남긴다.

왜 지역을 '_all' 로 적나
    collect 는 지역코드를 지정하지 않고(전국) 받았다. 지역별로 다른 값을 받은 적이 없으므로
    지역마다 다른 숫자를 만들어 넣으면 지어낸 값이 된다.
    그래서 '_all'(전국 기준) 한 벌만 내보내고, 앱이 모든 지역에 같은 값을 쓴다.
"""

from __future__ import annotations

import csv
import statistics
from datetime import date, datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
RAW_CSV = BASE_DIR / "data" / "prices_raw.csv"
OUT_DIR = BASE_DIR / "output"

# 장바구니 키 → 요리교실 앱의 품목ID.
# 앱에만 있고 장바구니에 없는 품목(전어·대하·무화과·고구마순·단호박·콩나물)은 여기 없다.
# 없는 것을 억지로 짝지으면 다른 재료의 값이 그 자리에 들어간다.
APP_KEY = {
    "baechu": "cabbage",
    "hobak": "zucchini",
    "gamja": "potato",
}

HEADER = ["기준일", "지역임시ID", "지역명", "권역", "품목ID", "품목명", "단위",
          "소매가", "평년대비", "전주대비", "뉴스언급", "근거메모", "출처"]


def _load(log) -> list[dict]:
    if not RAW_CSV.exists():
        raise FileNotFoundError(
            f"{RAW_CSV} 가 없습니다. 먼저 실행하세요:  python main.py collect --years 2")
    rows = []
    with open(RAW_CSV, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            try:
                r["d"] = datetime.strptime(r["date"], "%Y-%m-%d").date()
                r["p"] = int(r["price"])
            except (ValueError, KeyError, TypeError):
                continue
            rows.append(r)
    if not rows:
        raise ValueError("읽을 수 있는 행이 없습니다.")
    return rows


def _median_on(rows: list[dict], day: date) -> int | None:
    """같은 날 여러 줄(시장·품종별)이 오므로 중앙값을 그날의 대표값으로 쓴다."""
    vals = [r["p"] for r in rows if r["d"] == day]
    return int(statistics.median(vals)) if vals else None


def _mean_window(rows: list[dict], center: date, span: int) -> float | None:
    lo, hi = center - timedelta(days=span), center + timedelta(days=span)
    vals = [r["p"] for r in rows if lo <= r["d"] <= hi]
    return statistics.fmean(vals) if vals else None


def _pct(now: float, base: float | None) -> int | None:
    if not base:
        return None
    return round((now - base) / base * 100)


def run(log, region_name: str = "전국", area: str = "KAMIS 소매 평균") -> int:
    rows = _load(log)

    days = sorted({r["d"] for r in rows})
    latest = days[-1]
    print()
    print(f"  원자료   {len(rows):,}행 · {len(days)}개 날짜 · {days[0]} ~ {latest}")

    if len(days) < 30:
        print()
        print("  ⚠ 날짜가 너무 적습니다. 기간별 응답의 날짜가 제대로 안 들어온 상태입니다.")
        print("    전주·전년 대비를 계산할 수 없어 0 으로 둡니다.")
        print("    원인을 보려면:  python _debug_period.py")

    out: list[list] = []
    skipped: list[str] = []
    for key, app_key in APP_KEY.items():
        mine = [r for r in rows if r["key"] == key]
        if not mine:
            skipped.append(f"{key} (원자료에 없음)")
            continue

        name = mine[0].get("item") or key
        unit = mine[0].get("kind") or ""

        now = _median_on(mine, latest)
        if now is None:
            skipped.append(f"{name} (최근일 값 없음)")
            continue

        wk = _pct(now, _mean_window(mine, latest - timedelta(days=7), 3))
        try:
            a_year_ago = latest.replace(year=latest.year - 1)
        except ValueError:                      # 2월 29일
            a_year_ago = latest - timedelta(days=365)
        yr = _pct(now, _mean_window(mine, a_year_ago, 10))

        memo = f"KAMIS {len(mine)}행에서 계산. 같은 날 여러 줄은 중앙값을 썼다."
        if yr is None:
            memo += " 1년 전 자료가 없어 전년 대비는 비웠다."
        if wk is None:
            memo += " 1주 전 자료가 없어 전주 대비는 비웠다."

        out.append([latest.isoformat(), "_all", region_name, area,
                    app_key, name, unit, now,
                    yr if yr is not None else 0,
                    wk if wk is not None else 0,
                    0, memo, "KAMIS 실측 · 전년동기대비"])

    if not out:
        print()
        print("  내보낼 품목이 없습니다.")
        return 3

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"05_시세_{latest.isoformat()}.csv"
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(HEADER)
        w.writerows(out)

    print()
    print("=" * 68)
    print(f"  기준일 {latest} · 전국 소매 기준")
    print("=" * 68)
    print(f"  {'품목':<8}{'단위':<18}{'소매가':>9}{'전년':>8}{'전주':>8}")
    print("  " + "-" * 64)
    for r in out:
        print(f"  {r[5]:<8}{r[6][:16]:<18}{r[7]:>9,}{r[8]:>7}%{r[9]:>7}%")
    print()
    if skipped:
        print("  건너뛴 것: " + ", ".join(skipped))
    print(f"  앱 시세판 9품목 중 {len(out)}개만 실측입니다.")
    print("  전어·대하·무화과·고구마순·단호박·콩나물은 장바구니에 없어 예시값 그대로입니다.")
    print()
    print(f"  저장 → {path}")
    print("  이 파일을 구글시트 05_시세 에 붙여넣고, 앱에서 [시세 불러오기] 를 누르세요.")
    print()
    return 0
