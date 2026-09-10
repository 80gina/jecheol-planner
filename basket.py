"""요리교실 장바구니 — 무엇을 분석할지 한곳에 모아 둔다.

왜 따로 파일을 뒀나
    "분석 대상을 왜 이 9개로 골랐나"는 구술 평가에서 반드시 나온다.
    코드 여기저기 흩어져 있으면 대답할 수 없다. 이 파일 하나만 보여주면 된다.

품목 코드를 왜 안 적어 뒀나
    KAMIS 품목 코드는 외워서 적으면 틀린다. (A1-02 에서 모델 이름을 짐작했다가 404를 만난 경험)
    `python main.py codes` 로 KAMIS 가 알려주는 실제 코드를 받아
    data/item_codes.json 에 저장한 뒤, 그 파일을 보고 수집한다.

품목(item)과 품종(kind)을 왜 나눠 적나  ★ probe 결과를 보고 알게 된 것
    KAMIS 는 품목 아래 품종을 여러 개 둔다. 실제 응답이 이랬다.

        item_name=호박  →  kind_name=애호박(1개) / 쥬키니(1개)
        item_name=파    →  kind_name=대파(1kg)  / 쪽파(1kg)
        item_name=오이  →  kind_name=가시계통 / 다다기계통 / 취청

    "애호박"으로 찾으면 못 찾는다. 품목명은 "호박"이기 때문이다.
    품종을 지정하지 않으면 쪽파 값이 대파 자리에 섞여 들어온다.
    그래서 item(품목명)과 kind(품종에 포함될 말)를 따로 적는다.

kind 가 None 인 품목은 왜 비워 뒀나
    배추와 무는 계절마다 품종이 바뀐다. 9월에는 '여름(고랭지)'만 나오고
    겨울에는 '월동'이 나온다. 품종을 하나로 고정하면 2년 시계열이
    뚝뚝 끊긴다. 그래서 품목 단위로 받고, 어떤 품종이 왔는지는 기록만 한다.

등급은 왜 상품(04)으로 고정했나
    같은 품목에 상품·중품이 함께 온다. 섞이면 같은 날 값이 두 개가 되어
    시계열이 성립하지 않는다. 요리교실에서 실제로 사는 등급이 상품이라 그쪽으로 맞췄다.
"""

from __future__ import annotations

RANK_CODE = "04"        # 상품. 중품(05)과 섞이면 하루에 값이 두 개가 된다.

BASKET = [
    {
        "key": "baechu", "label": "배추", "item": "배추", "kind": None,
        "category": "채소류", "role": "국·김치",
        "why": "요리교실 5개 지역 전부에 들어가는 유일한 재료. 김장철 계절성이 가장 뚜렷할 것으로 보고 기준 품목으로 삼았다.",
    },
    {
        "key": "hobak", "label": "애호박", "item": "호박", "kind": "애호박",
        "category": "채소류", "role": "볶음",
        "why": "값이 작아 무시하기 쉽지만 12인 수업에서는 누적된다. 품목명이 '호박'이라 품종에서 애호박을 골라야 한다.",
    },
    {
        "key": "yangpa", "label": "양파", "item": "양파", "kind": None,
        "category": "채소류", "role": "양념·대조군",
        "why": "저장·유통 기간이 길어 계절 변동이 가장 작을 것으로 본 대조군. 계절성이 강한 품목들과 대조하기 위해 넣었다.",
    },
    {
        "key": "gamja", "label": "감자", "item": "감자", "kind": None,
        "category": "식량작물", "role": "면·밥",
        "why": "저장이 가능한 작물. 수확기와 가격 저점이 어긋나는지 보려고 골랐다.",
    },
    {
        "key": "goguma", "label": "고구마", "item": "고구마", "kind": None,
        "category": "식량작물", "role": "간식",
        "why": "감자와 같은 저장 작물이라 두 품목의 움직임이 닮았는지 비교한다.",
    },
    {
        "key": "mu", "label": "무", "item": "무", "kind": None,
        "category": "채소류", "role": "국물",
        "why": "배추와 함께 김장 수요를 받는 품목. 배추와 같은 시기에 오르는지 확인한다.",
    },
    {
        "key": "daepa", "label": "대파", "item": "파", "kind": "대파",
        "category": "채소류", "role": "양념",
        "why": "거의 모든 메뉴에 들어가는 공통 재료. 품목명이 '파'라 쪽파와 섞이지 않게 품종을 지정해야 한다.",
    },
    {
        "key": "sigeumchi", "label": "시금치", "item": "시금치", "kind": None,
        "category": "채소류", "role": "나물",
        "why": "겨울이 제철로 알려진 채소. '제철=저렴'이 맞는지 검증할 대표 사례로 골랐다.",
    },
    {
        "key": "oi", "label": "오이", "item": "오이", "kind": "다다기",
        "category": "채소류", "role": "반찬",
        "why": "여름이 제철인 채소. 시금치와 정반대 계절성이 나오는지 확인해 짝으로 본다. 품종은 가장 흔한 다다기계통으로 골랐다.",
    },
]

# 부류 이름 → KAMIS 부류 코드. 공식 문서에 고정으로 나와 있는 값이다.
CATEGORY_CODES = {
    "식량작물": "100",
    "채소류": "200",
    "특용작물": "300",
    "과일류": "400",
    "축산물": "500",
    "수산물": "600",
}

# ── 장바구니에서 뺀 것과 그 이유 (리포트·구술용)
EXCLUDED = [
    ("콩나물", "실내 재배라 계절성이 없는 대조군으로 넣었으나, probe 결과 KAMIS 채소류 "
               "품목 목록(31종)에 없었다. 추측으로 코드를 적지 않고 실제 응답을 확인한 뒤 "
               "양파로 교체했다."),
    ("전어·대하·무화과", "요리교실 재료이지만 수산물·과일류라 일별 시세가 촘촘하지 않다."),
]


def categories_used() -> list[str]:
    """장바구니가 실제로 쓰는 부류만 추린다. 필요 없는 조회를 줄이기 위해서."""
    seen: list[str] = []
    for item in BASKET:
        if item["category"] not in seen:
            seen.append(item["category"])
    return seen


def by_key(key: str) -> dict | None:
    for item in BASKET:
        if item["key"] == key:
            return item
    return None


def label(item: dict) -> str:
    """리포트·그래프에 쓸 이름.

    파생시키지 않고 명시해 둔다. 품종에서 뽑으면 오이가 '다다기'로 불린다.
    """
    return item["label"]


def summary_lines() -> list[str]:
    """CLI 에 보여줄 요약. 리포트에 붙일 표의 원본이기도 하다."""
    lines = ["번호  키          이름     KAMIS 품목  품종        부류      수업에서 맡는 자리"]
    lines.append("-" * 78)
    for i, it in enumerate(BASKET, 1):
        lines.append(
            f"{i:>2}.  {it['key']:<10}  {it['label']:<6}  {it['item']:<8}  "
            f"{(it['kind'] or '(전체)'):<9}  {it['category']:<7}  {it['role']}"
        )
    return lines
