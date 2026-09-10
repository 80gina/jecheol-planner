"""기상청 지상관측(ASOS) 일자료 — 가격이 왜 움직였는지 설명할 두 번째 데이터.

왜 날씨를 붙이나
    가격 그래프만 보면 "12월에 비싸다"까지는 말할 수 있지만
    "왜"에는 답할 수 없다. 배추가 얼면 출하량이 준다 — 이 연결을
    숫자로 확인하려면 기온이 있어야 한다.

    과제 요구인 "관찰(사실)과 해석(가설)의 구분"에서
    해석 쪽에 근거를 대주는 것이 이 데이터의 역할이다.

인증키
    공공데이터포털(data.go.kr) → '기상청_지상(종관, ASOS) 일자료 조회서비스'
    → 활용신청. 대개 자동승인이라 바로 받는다.
    받은 '일반 인증키(Decoding)' 를 .env 의 KMA_SERVICE_KEY 에 넣는다.
"""

from __future__ import annotations

import time
from datetime import date, timedelta

import requests

BASE_URL = "http://apis.data.go.kr/1360000/AsosDalyInfoService/getWthrDataList"

# 관측지점 번호. 요리교실이 열리는 지역들.
STATIONS = {
    "창원": "155",
    "순천": "174",   # 순천(웃장) 권역
    "전주": "146",
    "서산": "129",
    "강릉": "105",
}


class WeatherError(Exception):
    """기상 자료를 못 받았을 때."""


# 공공데이터포털이 돌려주는 오류 코드를 사람 말로 옮긴다.
# 숫자만 보면 뭘 고쳐야 할지 알 수 없어서, 코드마다 '다음에 할 일'까지 적었다.
REASON = {
    "30": ("등록되지 않은 서비스키",
           "가장 흔한 원인은 '아직 반영 전'입니다. 활용신청 직후에는 키가 바로 살아나지\n"
           "  않고 보통 30분~2시간(길면 하루) 걸립니다. 잠시 뒤 다시 실행해 보세요.\n"
           "  그래도 같으면 data.go.kr 마이페이지 → 오픈API → 개발계정에서\n"
           "  '기상청_지상(종관, ASOS) 일자료 조회서비스'가 목록에 있는지,\n"
           "  상태가 '승인'인지 확인하세요. 다른 API 키를 넣었을 수도 있습니다."),
    "31": ("기한 만료된 서비스키", "포털에서 활용기간을 연장하세요."),
    "22": ("서비스 요청 제한 횟수 초과",
           "하루 호출 한도를 넘겼습니다. 내일 다시 하거나 포털에서 한도를 늘리세요."),
    "20": ("서비스 접근 거부", "해당 서비스에 활용신청이 되어 있는지 확인하세요."),
    "10": ("잘못된 요청 변수", "지점 번호나 날짜 형식을 확인하세요."),
    "12": ("폐기된 서비스", "다른 서비스로 바꿔야 합니다."),
    # 아래는 기상청이 header.resultCode 로 주는 것들 (위와 번호 체계가 다르다)
    "99": ("날짜 범위 오류",
           "기상청 ASOS 일자료는 하루가 끝나야 확정되어 '전날까지'만 제공됩니다.\n"
           "  끝 날짜를 어제 이전으로 잡으세요."),
    "03": ("해당 자료 없음", "그 기간·지점에 관측 자료가 없습니다. 지점 번호를 확인하세요."),
}


def explain(text: str) -> str | None:
    """응답 본문에서 오류 코드를 찾아 무엇을 해야 하는지 알려준다."""
    import re

    m = re.search(r'"?returnReasonCode"?\s*[:>]\s*"?(\d+)"?', text)
    code = m.group(1) if m else None
    if not code:
        # 기상청은 정상 응답에도 resultCode 를 넣는다. "00" 은 성공이므로 건너뛴다.
        m = re.search(r'"?resultCode"?\s*[:>]\s*"?(\d+)"?', text)
        if m and m.group(1) not in ("00", "0"):
            code = m.group(1)
    if not code:
        m = re.search(r'"?errMsg"?\s*[:>]\s*"?([A-Z_]+)', text)
        if m and "NOT_REGISTERED" in m.group(1):
            code = "30"
    if not code or code not in REASON:
        return None
    title, todo = REASON[code]
    return f"[{code}] {title}\n  {todo}"


def _year_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """1년씩 잘라 부른다. 한 번에 너무 긴 기간을 달라면 거절당한다."""
    out, cur = [], start
    while cur <= end:
        stop = min(date(cur.year, 12, 31), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def daily(cfg: dict, log, service_key: str, station: str,
          start_day: str, end_day: str) -> list[dict]:
    """한 지점의 일별 기온·강수를 가져온다. 날짜는 YYYY-MM-DD."""
    s, e = date.fromisoformat(start_day), date.fromisoformat(end_day)
    req = cfg.get("request", {})
    timeout = req.get("timeout_sec", 15)
    rows: list[dict] = []

    for cs, ce in _year_chunks(s, e):
        params = {
            "serviceKey": service_key,
            "pageNo": 1,
            "numOfRows": 999,
            "dataType": "JSON",
            "dataCd": "ASOS",
            "dateCd": "DAY",
            "startDt": cs.strftime("%Y%m%d"),
            "endDt": ce.strftime("%Y%m%d"),
            "stnIds": station,
        }
        log.info("  기상청 조회 %s ~ %s (지점 %s)", cs, ce, station)
        try:
            res = requests.get(BASE_URL, params=params, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as err:
            raise WeatherError(f"연결 실패: {err.__class__.__name__}") from err

        hint = explain(res.text)
        if hint:
            raise WeatherError(hint)
        if res.status_code != 200:
            raise WeatherError(f"HTTP {res.status_code} — {res.text[:200]}")

        try:
            body = res.json()["response"]["body"]
        except (ValueError, KeyError):
            # 키가 틀리면 JSON 이 아니라 XML 오류가 온다. 원문을 보여줘야 고칠 수 있다.
            raise WeatherError(
                "응답을 읽지 못했습니다. 인증키가 맞는지 확인하세요.\n"
                f"  서버 응답: {res.text[:300]}")

        hint = explain(res.text)
        if hint:
            raise WeatherError(hint)

        items = body.get("items", {}).get("item", [])
        if isinstance(items, dict):
            items = [items]
        rows.extend(items)
        time.sleep(req.get("delay_sec", 0.7))

    return rows


def to_records(rows: list[dict], region: str) -> list[dict]:
    """필요한 칸만 골라 숫자로 바꾼다. 빈 칸('')은 결측으로 남긴다."""
    out = []
    for r in rows:
        tm = str(r.get("tm") or "").strip()
        if len(tm) != 10:
            continue
        out.append({
            "date": tm,
            "region": region,
            "avg_ta": _num(r.get("avgTa")),     # 평균기온 ℃
            "min_ta": _num(r.get("minTa")),     # 최저기온 ℃
            "max_ta": _num(r.get("maxTa")),     # 최고기온 ℃
            "sum_rn": _num(r.get("sumRn")) or 0.0,   # 일강수량 mm — 비 안 오면 빈칸
        })
    return out


def _num(v) -> float | None:
    s = str(v if v is not None else "").strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None
