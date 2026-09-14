"""수집한 가격 데이터를 정제하고, 분석하고, 그래프로 그린다.

    python main.py analyze

무엇을 하나
    1) 정제  — 중복·결측·이상치를 정해진 기준으로 처리한다
    2) 분석  — 이동평균 / 변화율 / 월별 집계 / 변동성 / 시계열 분해
    3) 그림  — images/ 에 PNG 5장
    4) 요약  — data/summary.json 에 리포트에 쓸 수치를 남긴다

왜 statsmodels 를 안 쓰나
    seasonal_decompose 를 부르면 한 줄로 끝나지만, "어떻게 분해했느냐"에
    답할 수 없게 된다. 고전적 분해는 이동평균 세 번이면 되므로 직접 짰다.
    의존성이 하나 줄어드는 것은 덤이다.
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.ticker import FuncFormatter

BASE_DIR = Path(__file__).resolve().parent
RAW_CSV = BASE_DIR / "data" / "prices_raw.csv"
WEATHER_CSV = BASE_DIR / "data" / "weather_raw.csv"
CLEAN_CSV = BASE_DIR / "data" / "prices_clean.csv"
SUMMARY = BASE_DIR / "data" / "summary.json"
IMG = BASE_DIR / "images"

# ── 정제 기준 — 리포트에 그대로 옮겨 적을 수 있게 한곳에 모아 둔다
GAP_FILL_MAX = 3        # 연속 3일 이하로 빈 구간만 메운다 (공휴일·조사 누락)
OUTLIER_WINDOW = 31     # 이상치 판정에 쓰는 이동중앙값 창 (홀수)
OUTLIER_RATIO = 0.5     # 이동중앙값 대비 ±50% 밖이면 이상치로 본다
MA_SHORT, MA_LONG = 7, 30
YEAR_DAYS = 261         # 1년치 영업일 수 (주말을 뺀 뒤의 한 해)
WEEK_DAYS = 5           # 한 주의 영업일 수 (월~금)

# ── 색: dataviz 기본 팔레트 (검증된 순서대로만 쓴다)
C1, C2, C3 = "#2a78d6", "#eb6834", "#1baf7a"
INK, INK2, INK3 = "#0b0b0b", "#52514e", "#8a8880"
GRID, SURFACE = "#e6e5e0", "#fcfcfb"


# ───────────────────────────────────────────── 한글 폰트

def setup_font(log=None) -> str:
    """한글이 네모(□□□)로 깨지지 않게 폰트를 잡는다.

    윈도우는 '맑은 고딕'이 기본으로 있다. 없으면 있는 것 중에서 고른다.
    """
    from matplotlib import font_manager

    have = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("Malgun Gothic", "AppleGothic", "NanumGothic",
                 "Noto Sans CJK KR", "Noto Sans KR", "Noto Sans CJK JP"):
        if name in have:
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False   # 마이너스 기호 깨짐 방지
            if log:
                log.info("한글 폰트: %s", name)
            return name
    if log:
        log.warning("한글 폰트를 못 찾았습니다. 그래프 글자가 깨질 수 있습니다.")
    return ""


def _style(ax, title="", ylab=""):
    ax.set_facecolor(SURFACE)
    ax.grid(True, color=GRID, linewidth=0.8, alpha=0.9)
    ax.set_axisbelow(True)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(GRID)
    ax.tick_params(colors=INK3, labelsize=9, length=0)
    if title:
        ax.set_title(title, color=INK, fontsize=12, loc="left", pad=10)
    if ylab:
        ax.set_ylabel(ylab, color=INK2, fontsize=9)


def _won(ax):
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f"{int(v):,}"))


# ───────────────────────────────────────────── 1) 정제

def clean(df: pd.DataFrame, log) -> tuple[pd.DataFrame, dict]:
    """결측과 이상치를 정해진 기준으로 처리한다. 무엇을 얼마나 고쳤는지 기록한다."""
    note: dict = {}

    before = len(df)
    df = df.drop_duplicates(subset=["date", "key"], keep="last")
    note["중복 제거"] = before - len(df)

    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values(["key", "date"])

    frames, stats = [], {}
    for key, g in df.groupby("key"):
        g = g.set_index("date")
        item = g["item"].iloc[0]

        # 영업일(월~금) 단위로 자리를 만든다.
        # 주말은 애초에 시세 조사를 하지 않으므로 '결측'이 아니다.
        # 주말까지 만들어 메우면 없는 거래를 지어내는 셈이 된다.
        full = pd.bdate_range(g.index.min(), g.index.max())
        s = g["price"].reindex(full)
        missing = int(s.isna().sum())

        # 이상치 — 31일 이동중앙값 대비 ±50% 밖. 평균이 아니라 중앙값을 쓰는 이유는
        # 평균은 튄 값 자체에 끌려가서 이상치를 못 잡기 때문이다.
        med = s.rolling(OUTLIER_WINDOW, center=True, min_periods=5).median()
        far = (s - med).abs() > med * OUTLIER_RATIO
        n_out = int(far.sum())
        s = s.mask(far)

        # 짧게 빈 구간만 잇는다. 길게 빈 구간을 이으면 없는 데이터를 지어내는 셈이다.
        filled = s.interpolate(method="linear", limit=GAP_FILL_MAX, limit_area="inside")
        n_fill = int(filled.notna().sum() - s.notna().sum())
        s = filled

        stats[item] = {"결측일": missing, "이상치": n_out, "보간": n_fill,
                       "최종 관측": int(s.notna().sum())}

        frames.append(pd.DataFrame({
            "date": full, "key": key, "item": item,
            "category": g["category"].iloc[0], "role": g["role"].iloc[0],
            "price": s.values,
        }))
        log.info("  %-6s 결측 %3d · 이상치 %2d · 보간 %3d → 관측 %d",
                 item, missing, n_out, n_fill, int(s.notna().sum()))

    note["품목별"] = stats
    out = pd.concat(frames, ignore_index=True).dropna(subset=["price"])
    return out, note


# ───────────────────────────────────────────── 2) 분석

def enrich(df: pd.DataFrame) -> pd.DataFrame:
    """이동평균과 변화율을 붙인다."""
    df = df.sort_values(["key", "date"]).copy()
    g = df.groupby("key")["price"]
    df[f"ma{MA_SHORT}"] = g.transform(lambda s: s.rolling(MA_SHORT, min_periods=3).mean())
    df[f"ma{MA_LONG}"] = g.transform(lambda s: s.rolling(MA_LONG, min_periods=10).mean())
    df["chg_1d"] = g.transform(lambda s: s.pct_change() * 100)
    df["chg_30d"] = g.transform(lambda s: s.pct_change(30) * 100)
    df["month"] = df["date"].dt.month
    return df


def seasonal_index(df: pd.DataFrame) -> pd.DataFrame:
    """월별 계절 지수 = (그 달 평균 ÷ 전체 평균) × 100.

    품목마다 값의 단위가 달라 원 단위로는 겹쳐 그릴 수 없다.
    100을 기준으로 바꾸면 '평소보다 몇 % 비싼 달인가'로 나란히 비교된다.
    """
    out = []
    for key, g in df.groupby("key"):
        base = g["price"].mean()
        m = g.groupby("month")["price"].mean() / base * 100
        for month, v in m.items():
            out.append({"key": key, "item": g["item"].iloc[0],
                        "month": int(month), "index": float(v)})
    return pd.DataFrame(out)


def volatility(df: pd.DataFrame) -> pd.DataFrame:
    """변동계수 = 표준편차 ÷ 평균 × 100.

    표준편차만 보면 '비싼 품목이 많이 흔들린다'는 당연한 결과만 나온다.
    평균으로 나눠야 값의 크기와 무관하게 비교할 수 있다.
    """
    rows = []
    for key, g in df.groupby("key"):
        p = g["price"]
        rows.append({"key": key, "item": g["item"].iloc[0],
                     "mean": float(p.mean()), "std": float(p.std()),
                     "cv": float(p.std() / p.mean() * 100),
                     "min": float(p.min()), "max": float(p.max()),
                     "spread": float(p.max() / p.min())})
    return pd.DataFrame(rows).sort_values("cv", ascending=False)


def pick_period(n: int) -> tuple[int, str]:
    """자료 길이에 맞는 분해 주기를 고른다.

    고전적 분해는 주기 길이만 한 창을 이동평균해서 추세를 뽑는다.
    그러려면 창이 자료 안에서 적어도 두 번은 온전히 채워져야 한다.
    한 번도 못 채우면 추세가 통째로 비고, 계절성·잔차도 따라서 빈다.

    KAMIS 기간 조회는 오늘 기준 최근 1년만 제공한다(2026-09 확인).
    따라서 지금 자료로는 연간 주기를 분해할 수 없다. 대신 주간(월~금)
    주기로 분해한다. 1년치면 약 48주기라 통계적으로 충분하다.
    """
    if n >= YEAR_DAYS * 2:
        return YEAR_DAYS, "연간"
    return WEEK_DAYS, "주간"


def decompose(s: pd.Series, period: int | None = None) -> dict:
    """고전적 가법 분해: 원본 = 추세 + 계절성 + 잔차.

    1) 추세   : 주기 길이만 한 중심 이동평균 — 한 주기를 통째로 평균 내면
                주기 성분이 서로 상쇄되고 긴 흐름만 남는다
    2) 계절성 : (원본 - 추세) 를 '주기 안 어느 위치인가' 로 묶어 평균
                연간 주기면 '몇 월 며칠', 주간 주기면 '무슨 요일'
    3) 잔차   : 남은 것. 설명되지 않는 부분이다

    period 를 주지 않으면 자료 길이를 보고 pick_period 가 고른다.
    """
    n = int(s.notna().sum())
    if period is None:
        period, cycle = pick_period(n)
    else:
        cycle = "연간" if period >= YEAR_DAYS else "주간"

    # min_periods 를 창 크기와 같게 둔다. 절반만 채워도 계산하게 하면
    # 구간 양 끝에서 없는 추세가 만들어져 보인다. 모르는 구간은 비워 두는 편이 정직하다.
    trend = s.rolling(period, center=True, min_periods=period).mean()
    detr = s - trend

    if cycle == "연간":
        phase = pd.Series(s.index.dayofyear, index=s.index)
        seas_map = detr.groupby(phase.values).mean()
        # 12월 31일과 1월 1일은 이어져 있다. 그냥 평활하면 연말연시에 턱이 생기므로
        # 앞뒤로 한 바퀴씩 이어 붙여 평활한 뒤 가운데만 쓴다.
        raw_idx = seas_map.index
        ring = pd.concat([seas_map, seas_map, seas_map])
        ring = ring.rolling(15, center=True, min_periods=1).mean()
        seas_map = ring.iloc[len(raw_idx):len(raw_idx) * 2]
        seas_map.index = raw_idx
    else:
        # 주간 주기는 위상이 월~금 다섯 개뿐이다. 평활할 이웃이 없으므로
        # 요일별 평균을 그대로 쓴다. 값이 다섯 개라 표로도 읽힌다.
        phase = pd.Series(s.index.dayofweek, index=s.index)
        seas_map = detr.groupby(phase.values).mean()

    seasonal = pd.Series(phase.values, index=s.index).map(seas_map)
    resid = s - trend - seasonal

    # 설명된 비중 — 잔차가 작을수록 분해가 잘 들어맞은 것이다.
    ok = resid.notna()
    strength = None
    if ok.sum() > 10 and s[ok].var() > 0:
        strength = round(float(1 - resid[ok].var() / s[ok].var()) * 100, 1)

    return {"observed": s, "trend": trend, "seasonal": seasonal, "resid": resid,
            "period": period, "cycle": cycle, "n": n, "strength": strength,
            "phase_mean": {int(k): round(float(v), 1) for k, v in seas_map.items()}}


def temp_vs_price(df: pd.DataFrame, wx: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """월평균 기온과 월별 가격지수를 짝지어 상관을 본다.

    왜 산점도인가
        기온과 가격은 단위가 완전히 다르다(℃ 와 원). 한 그림에 세로축을
        둘 두면(이중축) 두 선의 교차점이 아무 뜻도 없는데 뜻이 있어 보인다.
        가로축을 기온, 세로축을 가격지수로 놓으면 축은 하나씩만 쓰면서
        관계를 그대로 볼 수 있다.

    ⚠️ 상관은 인과가 아니다
        기온이 낮은 달에 값이 비싸다 해도, 추워서 비싼 것인지
        김장 수요가 몰려서 비싼 것인지 이 그림만으로는 못 가른다.
        리포트에서는 '관찰'로만 쓰고, 원인은 '가설'로 분리해 적는다.
    """
    wx = wx.copy()
    wx["date"] = pd.to_datetime(wx["date"])
    wx["month"] = wx["date"].dt.month
    mt = wx.groupby("month")["avg_ta"].mean()

    rows, corr = [], {}
    for key, g in df.groupby("key"):
        base = g["price"].mean()
        mp = g.groupby("month")["price"].mean() / base * 100
        joined = pd.concat([mt.rename("temp"), mp.rename("index")], axis=1).dropna()
        if len(joined) < 6:
            continue
        corr[key] = {"item": g["item"].iloc[0],
                     "r": float(joined["temp"].corr(joined["index"]))}
        for m, r in joined.iterrows():
            rows.append({"key": key, "item": g["item"].iloc[0], "month": int(m),
                         "temp": float(r["temp"]), "index": float(r["index"])})
    return pd.DataFrame(rows), corr


# ───────────────────────────────────────────── 3) 그림

def fig_trend(df: pd.DataFrame, path: Path):
    """9품목 전체 추이 — 한 판에 9줄을 겹치면 아무것도 안 보인다. 9칸으로 나눈다."""
    items = df.groupby("key")["item"].first()
    keys = list(items.index)
    fig, axes = plt.subplots(3, 3, figsize=(13, 8.5), sharex=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, key in zip(axes.flat, keys):
        g = df[df["key"] == key]
        ax.plot(g["date"], g["price"], color=C1, linewidth=1.2)
        _style(ax, items[key])
        _won(ax)
    import matplotlib.dates as mdates
    for ax in axes[-1]:
        ax.xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 7)))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    for ax in axes.flat[len(keys):]:
        ax.set_visible(False)
    fig.suptitle("품목별 소매가격 추이 (일별)", x=0.012, ha="left",
                 fontsize=15, color=INK, y=0.985)
    fig.text(0.012, 0.945, "세로축 단위가 품목마다 다릅니다. 모양을 비교하는 그림입니다.",
             fontsize=9.5, color=INK2)
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def fig_moving_average(df: pd.DataFrame, key: str, path: Path):
    g = df[df["key"] == key].sort_values("date")
    name = g["item"].iloc[0]
    fig, ax = plt.subplots(figsize=(12, 5.2))
    fig.patch.set_facecolor(SURFACE)
    ax.plot(g["date"], g["price"], color=INK3, linewidth=0.8, alpha=0.55, label="일별 원본")
    ax.plot(g["date"], g[f"ma{MA_SHORT}"], color=C1, linewidth=2, label=f"{MA_SHORT}일 이동평균")
    ax.plot(g["date"], g[f"ma{MA_LONG}"], color=C2, linewidth=2, label=f"{MA_LONG}일 이동평균")
    _style(ax, f"{name} — 원본과 이동평균", "원")
    _won(ax)
    ax.legend(frameon=False, fontsize=10, labelcolor=INK2, loc="upper left")
    last = g.dropna(subset=[f"ma{MA_LONG}"]).iloc[-1]
    ax.annotate(f"{int(last[f'ma{MA_LONG}']):,}원", (last["date"], last[f"ma{MA_LONG}"]),
                xytext=(8, 0), textcoords="offset points",
                color=C2, fontsize=10, va="center")
    ax.margins(x=0.045)   # 오른쪽 끝 라벨이 잘리지 않게 여백을 둔다
    fig.tight_layout()
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def fig_seasonality(si: pd.DataFrame, keys: list[str], path: Path):
    fig, ax = plt.subplots(figsize=(11, 5.2))
    fig.patch.set_facecolor(SURFACE)
    ax.axhline(100, color=INK3, linewidth=1, linestyle="--", alpha=0.7)
    ax.text(12.15, 100, "연평균", color=INK3, fontsize=9, va="center")
    for key, color in zip(keys, (C1, C2, C3)):
        g = si[si["key"] == key].sort_values("month")
        if g.empty:
            continue
        name = g["item"].iloc[0]
        ax.plot(g["month"], g["index"], color=color, linewidth=2.2,
                marker="o", markersize=8, markeredgecolor=SURFACE,
                markeredgewidth=2, label=name)
        end = g.iloc[-1]
        ax.annotate(name, (end["month"], end["index"]), xytext=(9, 0),
                    textcoords="offset points", color=color,
                    fontsize=10.5, fontweight="bold", va="center")
    _style(ax, "월별 계절 지수 — 연평균을 100으로 놓았을 때", "지수")
    ax.set_xticks(range(1, 13))
    ax.set_xticklabels([f"{m}월" for m in range(1, 13)])
    ax.set_xlim(0.6, 13.6)
    ax.legend(frameon=False, fontsize=10, labelcolor=INK2, loc="upper center", ncol=3)
    fig.tight_layout()
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def fig_volatility(vol: pd.DataFrame, path: Path):
    fig, ax = plt.subplots(figsize=(10, 5.4))
    fig.patch.set_facecolor(SURFACE)
    v = vol.sort_values("cv")
    y = np.arange(len(v))
    ax.barh(y, v["cv"], color=C1, height=0.62)
    ax.set_yticks(y)
    ax.set_yticklabels(v["item"], fontsize=10.5, color=INK)
    for i, cv in enumerate(v["cv"]):
        ax.text(cv + 0.5, i, f"{cv:.1f}%", va="center", fontsize=10, color=INK2)
    _style(ax, "품목별 가격 변동성 (변동계수 = 표준편차 ÷ 평균)")
    ax.set_xlim(0, v["cv"].max() * 1.18)
    ax.set_xlabel("변동계수 (%)", color=INK2, fontsize=9)
    ax.grid(axis="y", visible=False)
    fig.tight_layout()
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def fig_decompose(parts: dict, name: str, path: Path):
    cycle = parts.get("cycle", "연간")
    period = parts.get("period", YEAR_DAYS)
    labels = [("observed", "원본", C1), ("trend", "추세", C2),
              ("seasonal", f"{cycle} 주기", C3), ("resid", "잔차", INK3)]
    fig, axes = plt.subplots(4, 1, figsize=(12, 9), sharex=True)
    fig.patch.set_facecolor(SURFACE)
    for ax, (k, lab, color) in zip(axes, labels):
        ax.plot(parts[k].index, parts[k].values, color=color, linewidth=1.4)
        if k in ("seasonal", "resid"):
            ax.axhline(0, color=GRID, linewidth=1)
        if k == "trend" and cycle == "연간":
            ax.text(0.995, 0.06,
                    f"양 끝은 {period}영업일 창이 다 차지 않아 비어 있습니다",
                    transform=ax.transAxes, ha="right", fontsize=9, color=INK3)
        _style(ax, lab)
        _won(ax)
    import matplotlib.dates as mdates
    axes[-1].xaxis.set_major_locator(mdates.MonthLocator(bymonth=(1, 4, 7, 10)))
    axes[-1].xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    st = parts.get("strength")
    tail = f"  ·  설명된 비중 {st}%" if st is not None else ""
    fig.suptitle(f"{name} — 시계열 분해 (원본 = 추세 + {cycle} 주기 + 잔차){tail}",
                 x=0.012, ha="left", fontsize=15, color=INK, y=0.988)
    if cycle == "주간":
        fig.text(0.012, 0.955,
                 f"자료가 1년(1주기)뿐이라 연간 주기는 분해할 수 없어 "
                 f"주간({period}영업일) 주기로 분해했습니다. "
                 "월별 계절 지수는 03번 그래프를 보십시오.",
                 ha="left", fontsize=9.5, color=INK3)
        fig.tight_layout(rect=[0, 0, 1, 0.945])
    else:
        fig.tight_layout(rect=[0, 0, 1, 0.955])
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def fig_temp_price(tp: pd.DataFrame, corr: dict, keys: list[str], path: Path):
    fig, ax = plt.subplots(figsize=(11, 5.6))
    fig.patch.set_facecolor(SURFACE)
    ax.axhline(100, color=INK3, linewidth=1, linestyle="--", alpha=0.6)
    for key, color in zip(keys, (C1, C2, C3)):
        g = tp[tp["key"] == key].sort_values("month")
        if g.empty:
            continue
        name = g["item"].iloc[0]
        r = corr.get(key, {}).get("r")
        ax.plot(g["temp"], g["index"], color=color, linewidth=1.4, alpha=0.55)
        ax.scatter(g["temp"], g["index"], s=110, color=color,
                   edgecolor=SURFACE, linewidth=2, zorder=3,
                   label=f"{name}  (상관 r={r:+.2f})" if r is not None else name)
        for _, row in g.iterrows():
            ax.annotate(f"{row['month']}", (row["temp"], row["index"]),
                        fontsize=7.5, color=SURFACE, ha="center", va="center",
                        zorder=4, fontweight="bold")
    _style(ax, "월평균 기온과 가격지수의 관계", "가격지수 (연평균=100)")
    ax.set_xlabel("월평균 기온 (℃)", color=INK2, fontsize=9)
    ax.legend(frameon=False, fontsize=10, labelcolor=INK2, loc="best")
    fig.text(0.012, 0.015, "점 안의 숫자는 월입니다. 상관은 관계의 세기일 뿐 "
             "원인을 말해 주지 않습니다.", fontsize=9, color=INK3)
    fig.tight_layout(rect=[0, 0.04, 1, 1])
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


# ───────────────────────────────────────────── 실행

def run(log, focus: str = "baechu") -> int:
    if not RAW_CSV.exists():
        print(f"[ERROR] {RAW_CSV.name} 이 없습니다. 먼저:  python main.py collect")
        return 2

    setup_font(log)
    IMG.mkdir(parents=True, exist_ok=True)

    raw = pd.read_csv(RAW_CSV)
    log.info("원본 %d행 / 품목 %d개", len(raw), raw["key"].nunique())

    log.info("정제 시작")
    df, note = clean(raw, log)
    df = enrich(df)
    df.to_csv(CLEAN_CSV, index=False, encoding="utf-8-sig")
    log.info("정제 완료 %d행 → %s", len(df), CLEAN_CSV.name)

    si = seasonal_index(df)
    vol = volatility(df)

    # 보고서 부록에 그대로 붙일 수 있게 표로도 남긴다.
    si_wide = si.pivot(index="item", columns="month", values="index").round(1)
    si_wide.to_csv(BASE_DIR / "data" / "seasonal_index.csv", encoding="utf-8-sig")
    vol.round(1).to_csv(BASE_DIR / "data" / "volatility.csv",
                        index=False, encoding="utf-8-sig")

    if focus not in set(df["key"]):
        focus = df["key"].iloc[0]
    fs = (df[df["key"] == focus].set_index("date")["price"]
          .asfreq("B").interpolate(limit=GAP_FILL_MAX))
    parts = decompose(fs)
    focus_name = df[df["key"] == focus]["item"].iloc[0]

    # 계절성이 가장 뚜렷한 품목과 가장 평평한 품목을 뽑아 함께 그린다
    swing = (si.groupby("key")["index"].max() - si.groupby("key")["index"].min())
    picks = [swing.idxmax(), swing.idxmin()]
    third = swing.drop(picks).idxmax() if len(swing) > 2 else None
    if third:
        picks.insert(1, third)

    log.info("그래프 그리는 중")
    fig_trend(df, IMG / "01_price_trend.png")
    fig_moving_average(df, focus, IMG / "02_moving_average.png")
    fig_seasonality(si, picks, IMG / "03_seasonality.png")
    fig_volatility(vol, IMG / "04_volatility.png")
    fig_decompose(parts, focus_name, IMG / "05_decompose.png")

    # 기상 자료가 있으면 한 장 더. 없어도 나머지는 그대로 나온다.
    weather_note = None
    if WEATHER_CSV.exists():
        wx = pd.read_csv(WEATHER_CSV)
        tp, corr = temp_vs_price(df, wx)
        if not tp.empty:
            fig_temp_price(tp, corr, picks, IMG / "06_temp_vs_price.png")
            weather_note = {"지역": str(wx["region"].iloc[0]),
                            "행수": len(wx), "상관": corr}
            log.info("기상 자료 결합 완료 (%s, %d행)", wx["region"].iloc[0], len(wx))
    else:
        log.info("기상 자료 없음 — 06 그래프는 건너뜁니다 (python main.py weather)")

    summary = {
        "기간": {"시작": str(df["date"].min().date()), "끝": str(df["date"].max().date())},
        "행수": {"원본": len(raw), "정제후": len(df)},
        "정제": note,
        "정제기준": {
            "달력": "월~금 영업일 기준. 주말은 시세 조사가 없어 결측으로 세지 않는다",
            "결측": f"연속 {GAP_FILL_MAX}일 이하만 선형보간, 그 이상은 결측 유지",
            "이상치": f"{OUTLIER_WINDOW}일 이동중앙값 대비 ±{int(OUTLIER_RATIO*100)}% 밖",
        },
        "자료범위": {
            "확인": "KAMIS 기간 조회는 오늘 기준 최근 1년만 제공한다 "
                    "(2026-09-14 probe_history.py 로 확인). "
                    "범위 밖 구간은 '자료 없음'이 아니라 HTTP 500 으로 응답한다",
            "영향": "연간 계절성의 반복성은 1주기만 관측되어 검증할 수 없다. "
                    "월별 계절지수는 '관측된 한 해의 모양'으로 읽어야 한다",
        },
        "분해방식": {
            "주기": parts.get("cycle"),
            "창(영업일)": parts.get("period"),
            "관측수": parts.get("n"),
            "설명된비중%": parts.get("strength"),
            "위상평균(원)": parts.get("phase_mean"),
            "선택이유": "고전적 분해는 주기 길이만 한 창이 자료 안에서 두 번 이상 "
                        "채워져야 추세와 주기를 가를 수 있다. "
                        f"자료가 {parts.get('n')}영업일이라 연간({YEAR_DAYS}일) 창은 "
                        "그 조건을 못 채워 추세가 사실상 빈다. "
                        f"주간({WEEK_DAYS}일) 주기는 약 {parts.get('n', 0) // WEEK_DAYS}주기라 충분하다",
        },
        "변동성": vol.to_dict("records"),
        "계절지수": {
            k: {"최고월": int(g.loc[g["index"].idxmax(), "month"]),
                "최저월": int(g.loc[g["index"].idxmin(), "month"]),
                "진폭": round(float(g["index"].max() - g["index"].min()), 1),
                "품목": g["item"].iloc[0]}
            for k, g in si.groupby("key")},
        "기상": weather_note,
        "분해대상": focus_name,
        "분해": {
            "추세_시작": float(parts["trend"].dropna().iloc[0]) if parts["trend"].notna().any() else None,
            "추세_끝": float(parts["trend"].dropna().iloc[-1]) if parts["trend"].notna().any() else None,
            "주기성분_진폭": float(parts["seasonal"].max() - parts["seasonal"].min()),
            "잔차_표준편차": float(parts["resid"].std()),
        },
    }
    SUMMARY.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print("=" * 66)
    print("  분석 완료")
    print("=" * 66)
    print(f"  기간   {summary['기간']['시작']} ~ {summary['기간']['끝']}")
    print(f"  행수   원본 {len(raw):,} → 정제 후 {len(df):,}")
    print()
    print("  변동성이 큰 품목 (변동계수)")
    for r in vol.head(3).to_dict("records"):
        print(f"    {r['item']:<6} {r['cv']:>5.1f}%   "
              f"최저 {int(r['min']):,}원 → 최고 {int(r['max']):,}원 ({r['spread']:.1f}배)")
    print()
    print("  계절 진폭이 큰 품목 (최고월 지수 - 최저월 지수)")
    for k in swing.sort_values(ascending=False).head(3).index:
        s = summary["계절지수"][k]
        print(f"    {s['품목']:<6} 진폭 {s['진폭']:>5.1f}p   "
              f"최고 {s['최고월']}월 · 최저 {s['최저월']}월")
    print()
    if weather_note:
        print("  기온과의 상관 (음수 = 추울수록 비싸다)")
        for k, v in sorted(weather_note["상관"].items(),
                           key=lambda x: x[1]["r"])[:3]:
            print(f"    {v['item']:<6} r = {v['r']:+.2f}")
        print()
    n = 6 if weather_note else 5
    print(f"  그래프 {n}장 → {IMG}")
    print(f"  요약 수치  → {SUMMARY}")
    print()
    return 0
