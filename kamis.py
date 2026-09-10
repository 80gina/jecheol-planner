"""KAMIS(농산물유통정보) 오픈API 클라이언트.

무엇을 가져오나
    품목별·지역별 도매/소매 가격. 평년·전년·전월·전주 대비 값도 함께 온다.
    그래서 "지금 싼 식재료"를 가격 하나가 아니라 **평소 대비 얼마나 싼가**로 볼 수 있다.

주의 — 이 파일은 '응답이 이렇게 올 것이다'를 가정하지 않는다
    공개 API는 계정·시기에 따라 필드 이름이 다를 수 있다.
    그래서 `probe()` 로 실제 응답을 먼저 눈으로 확인한 뒤 파서를 맞춘다.
    A1-02 에서 모델 이름을 짐작했다가 404를 만난 경험에서 나온 방식이다.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import requests

# KAMIS 부류 코드 — probe 로 실제 확인한 뒤 확정한다
CATEGORY_CODES = {
    "식량작물": "100",
    "채소류": "200",
    "특용작물": "300",
    "과일류": "400",
    "축산물": "500",
    "수산물": "600",
}


class KamisError(Exception):
    """가격 조회를 포기해야 할 때."""


def _params(cfg: dict, cert_key: str, cert_id: str, **extra) -> dict:
    base = {
        "p_cert_key": cert_key,
        "p_cert_id": cert_id,
        "p_returntype": "json",
    }
    base.update(extra)
    return base


def _get(cfg: dict, log, params: dict, max_retry: int | None = None) -> dict | str:
    """타임아웃·재시도를 갖춘 GET. (bapsang-trend 의 원칙 그대로)

    4xx = 내 잘못 → 즉시 포기
    5xx / 타임아웃 = 저쪽 사정 → 지수 백오프 재시도
    """
    req = cfg.get("request", {})
    url = cfg.get("kamis", {}).get("base_url", "")
    timeout = req.get("timeout_sec", 15)
    if max_retry is None:
        max_retry = req.get("max_retry", 3)
    headers = {"User-Agent": req.get("user_agent", "JecheolPlanner/1.0")}

    for attempt in range(1, max_retry + 1):
        try:
            res = requests.get(url, params=params, headers=headers, timeout=timeout)
        except (requests.Timeout, requests.ConnectionError) as e:
            wait = 2 ** attempt
            log.warning("KAMIS 연결 실패 (%d/%d): %s. %d초 뒤 재시도합니다.",
                        attempt, max_retry, e.__class__.__name__, wait)
            time.sleep(wait)
            continue

        if res.status_code == 200:
            res.encoding = res.apparent_encoding or "utf-8"
            text = res.text.strip()
            try:
                return res.json()
            except ValueError:
                # JSON을 요청했는데 XML/HTML 이 오는 경우가 있다. 원문을 그대로 넘긴다.
                return text

        if 400 <= res.status_code < 500:
            raise KamisError(
                f"요청이 거부되었습니다 (HTTP {res.status_code}) — 재시도하지 않습니다.\n"
                f"  서버 응답: {res.text[:300]}"
            )

        wait = 2 ** attempt
        log.warning("KAMIS 서버 오류 HTTP %d (%d/%d). %d초 뒤 재시도합니다.",
                    res.status_code, attempt, max_retry, wait)
        time.sleep(wait)

    raise KamisError(f"{max_retry}회 시도했지만 응답을 받지 못했습니다.")


def probe(cfg: dict, log, cert_key: str, cert_id: str,
          regday: str, category: str = "채소류",
          country_code: str = "", cls_code: str = "01") -> dict | str:
    """실제 응답을 그대로 받아 온다. 파서를 맞추기 전 확인용.

    성공하면 응답 원문을 돌려주고, 호출자가 파일로 저장해 눈으로 본다.
    """
    params = _params(
        cfg, cert_key, cert_id,
        action="dailyPriceByCategoryList",
        p_product_cls_code=cls_code,
        p_item_category_code=CATEGORY_CODES.get(category, "200"),
        p_regday=regday,
        p_convert_kg_yn=cfg.get("kamis", {}).get("convert_kg", "N"),
    )
    if country_code:
        params["p_country_code"] = country_code

    log.info("KAMIS 조회: %s / %s / %s%s",
             regday, category, "소매" if cls_code == "01" else "도매",
             f" / 지역코드 {country_code}" if country_code else " / 지역 미지정")
    return _get(cfg, log, params)


def save_raw(payload, out_dir: Path, name: str, log) -> Path:
    """받은 응답을 그대로 파일에 남긴다. (raw 보존 원칙)"""
    out_dir.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, (dict, list)):
        path = out_dir / f"{name}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    else:
        path = out_dir / f"{name}.txt"
        path.write_text(str(payload), encoding="utf-8")
    log.info("응답 원문 저장: %s (%d바이트)", path.name, path.stat().st_size)
    return path


def summarize_shape(payload, depth: int = 0, max_depth: int = 3) -> list[str]:
    """응답의 '모양'만 요약한다. 필드 이름을 눈으로 확인하기 위해."""
    pad = "  " * depth
    lines: list[str] = []
    if depth > max_depth:
        return [pad + "…"]
    if isinstance(payload, dict):
        for k, v in list(payload.items())[:20]:
            if isinstance(v, (dict, list)):
                lines.append(f"{pad}{k}:")
                lines += summarize_shape(v, depth + 1, max_depth)
            else:
                val = str(v)
                lines.append(f"{pad}{k} = {val[:40]}")
    elif isinstance(payload, list):
        lines.append(f"{pad}[리스트 {len(payload)}개]")
        if payload:
            lines += summarize_shape(payload[0], depth + 1, max_depth)
    else:
        lines.append(f"{pad}{str(payload)[:80]}")
    return lines


# ─────────────────────────────────────────────────────────────────
# 여기서부터: 시계열 분석 과제용으로 추가한 부분
# ─────────────────────────────────────────────────────────────────
#
# 위쪽 probe() 는 "하루치 스냅샷"만 가져온다. 시계열이 되려면 기간이 필요하다.
# KAMIS 는 그 용도로 periodProductList 라는 별도 액션을 제공한다.
#
# ⚠️ 주의 — 두 액션은 파라미터 이름 규칙이 다르다
#     dailyPriceByCategoryList : p_item_category_code  (밑줄 있음)
#     periodProductList        : p_itemcategorycode    (밑줄 없음)
#   같은 API인데 다르다. 실제로 겪는 흔한 오류라 주석으로 못박아 둔다.


def list_items(cfg: dict, log, cert_key: str, cert_id: str,
               regday: str, category_code: str,
               cls_code: str = "01") -> list[dict]:
    """어떤 부류에 어떤 품목이 있고, 코드가 무엇인지 KAMIS 에게 직접 물어본다.

    품목 코드를 외워서 적으면 틀린다. 받아 적는다.
    """
    params = _params(
        cfg, cert_key, cert_id,
        action="dailyPriceByCategoryList",
        p_product_cls_code=cls_code,
        p_item_category_code=category_code,
        p_regday=regday,
        p_convert_kg_yn="N",
    )
    payload = _get(cfg, log, params)
    rows = _rows(payload)

    # 품목 단위로 접지 않고 (품목, 품종, 등급) 조합을 그대로 돌려준다.
    # 접어 버리면 '호박'의 애호박과 쥬키니를 구분할 수 없다.
    out: list[dict] = []
    for r in rows:
        code = str(r.get("item_code") or r.get("itemcode") or "").strip()
        name = str(r.get("item_name") or r.get("itemname") or "").strip()
        if not code or not name:
            continue
        out.append({
            "item_code": code,
            "item_name": name,
            "kind_code": str(r.get("kind_code") or r.get("kindcode") or "").strip(),
            "kind_name": str(r.get("kind_name") or r.get("kindname") or "").strip(),
            "rank_code": str(r.get("rank_code") or r.get("productrankcode") or "").strip(),
            "rank_name": str(r.get("rank") or "").strip(),
            "unit": str(r.get("unit") or "").strip(),
        })
    return out


def period_price(cfg: dict, log, cert_key: str, cert_id: str,
                 start_day: str, end_day: str,
                 category_code: str, item_code: str,
                 kind_code: str = "", rank_code: str = "",
                 country_code: str = "", cls_code: str = "01") -> list[dict]:
    """한 품목의 기간별 가격을 가져온다. 이것이 시계열의 원재료다.

    날짜는 YYYY-MM-DD.
    """
    params = _params(
        cfg, cert_key, cert_id,
        action="periodProductList",
        p_productclscode=cls_code,           # 밑줄 없음 — 위 주의 참고
        p_startday=start_day,
        p_endday=end_day,
        p_itemcategorycode=category_code,
        p_itemcode=item_code,
        p_convert_kg_yn=cfg.get("kamis", {}).get("convert_kg", "N"),
    )
    if kind_code:
        params["p_kindcode"] = kind_code
    if rank_code:
        params["p_productrankcode"] = rank_code
    if country_code:
        params["p_countrycode"] = country_code

    log.info("  기간 조회 %s ~ %s (품목코드 %s)", start_day, end_day, item_code)
    # 재시도 1번만.
    #   시간 초과는 대개 "이 구간이 너무 크다"는 뜻이라, 같은 크기로 다시 물어도 또 끊긴다.
    #   여러 번 기다리느니 빨리 포기하고 호출자가 구간을 쪼개는 편이 빠르다.
    payload = _get(cfg, log, params, max_retry=1)
    return _rows(payload)


def _rows(payload) -> list[dict]:
    """응답에서 '가격 줄 목록'만 꺼낸다.

    KAMIS 응답 모양이 액션마다·시기마다 조금씩 다르다.
    그래서 '어디에 있든 찾아낸다'는 방식으로 짰다. 한 군데를 가정하지 않는다.
    """
    if isinstance(payload, str):
        return []

    def dig(node):
        if isinstance(node, list):
            if node and isinstance(node[0], dict):
                return node
            for x in node:
                found = dig(x)
                if found:
                    return found
            return []
        if isinstance(node, dict):
            for key in ("item", "items", "data", "price", "list"):
                if key in node:
                    found = dig(node[key])
                    if found:
                        return found
            for v in node.values():
                found = dig(v)
                if found:
                    return found
        return []

    return dig(payload)


def error_message(payload) -> str | None:
    """KAMIS 는 실패해도 HTTP 200 을 준다. 본문 안의 error_code 를 봐야 한다."""
    if isinstance(payload, dict):
        for key in ("error_code", "errorCode", "result_code"):
            if key in payload:
                code = str(payload[key])
                return None if code in ("000", "0", "OK") else f"KAMIS error_code={code}"
        for v in payload.values():
            if isinstance(v, dict):
                msg = error_message(v)
                if msg:
                    return msg
    return None


def split_range(start_day: str, end_day: str) -> tuple[tuple[str, str], tuple[str, str]] | None:
    """구간을 절반으로 나눈다. 15일보다 짧아지면 더 나누지 않는다.

    왜 필요한가
        KAMIS 기간 조회는 한 번에 돌려줄 수 있는 양에 한계가 있다.
        그 한계가 문서에 안 나와 있어서, 넘으면 오류 대신 **빈 응답**이 온다.
        그래서 "빈 응답이면 절반으로 쪼개 다시 물어본다"로 짰다.
        한계값을 짐작해 박아 넣는 것보다 확실하다.
    """
    from datetime import date, timedelta

    s = date.fromisoformat(start_day)
    e = date.fromisoformat(end_day)
    span = (e - s).days
    if span < 15:
        return None
    mid = s + timedelta(days=span // 2)
    return (s.isoformat(), mid.isoformat()), \
           ((mid + timedelta(days=1)).isoformat(), e.isoformat())


def day_chunks(start_day: str, end_day: str, days: int) -> list[tuple[str, str]]:
    """일수로 잘라 나눈다. 서버가 받아주는 크기를 알아낸 뒤 그 크기로 쓴다."""
    from datetime import date, timedelta

    s = date.fromisoformat(start_day)
    e = date.fromisoformat(end_day)
    out: list[tuple[str, str]] = []
    cur = s
    step = max(int(days), 5)
    while cur <= e:
        stop = min(cur + timedelta(days=step), e)
        out.append((cur.isoformat(), stop.isoformat()))
        cur = stop + timedelta(days=1)
    return out


def month_chunks(start_day: str, end_day: str, months: int = 6) -> list[tuple[str, str]]:
    """긴 기간을 잘라 나눈다.

    2년치를 한 번에 달라고 하면 서버가 시간 초과로 끊는 경우가 있다.
    작게 나눠 여러 번 부르는 편이 결과적으로 빠르고 확실하다.
    """
    from datetime import date, timedelta

    s = date.fromisoformat(start_day)
    e = date.fromisoformat(end_day)
    out: list[tuple[str, str]] = []
    cur = s
    while cur <= e:
        y, m = cur.year, cur.month + months
        while m > 12:
            y, m = y + 1, m - 12
        try:
            nxt = date(y, m, cur.day)
        except ValueError:
            nxt = date(y, m, 28)
        stop = min(nxt - timedelta(days=1), e)
        out.append((cur.isoformat(), stop.isoformat()))
        cur = stop + timedelta(days=1)
    return out
