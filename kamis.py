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


def _get(cfg: dict, log, params: dict) -> dict | str:
    """타임아웃·재시도를 갖춘 GET. (bapsang-trend 의 원칙 그대로)

    4xx = 내 잘못 → 즉시 포기
    5xx / 타임아웃 = 저쪽 사정 → 지수 백오프 재시도
    """
    req = cfg.get("request", {})
    url = cfg.get("kamis", {}).get("base_url", "")
    timeout = req.get("timeout_sec", 15)
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
