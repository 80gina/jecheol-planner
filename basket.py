"""요리교실 장바구니 — 무엇을 분석할지 한곳에 모아 둔다.

왜 따로 파일을 뒀나
    "분석 대상을 왜 이 9개로 골랐나"는 구술 평가에서 반드시 나온다.
    코드 여기저기 흩어져 있으면 대답할 수 없다. 이 파일 하나만 보여주면 된다.

품목 코드를 왜 안 적어 뒀나
    KAMIS 품목 코드는 외워서 적으면 틀린다. (A1-02 에서 모델 이름을 짐작했다가 404를 만난 경험)
    그래서 `python main.py codes` 로 KAMIS 가 알려주는 실제 코드를 받아
    data/item_codes.json 에 저장한 뒤, 그 파일을 보고 수집한다.
"""

from __future__ import annotations

# 요리교실 9회차에서 실제로 쓰는 재료.
#   name       : KAMIS 품목명과 맞춰볼 이름 (여러 개면 앞에서부터 시도)
#   category   : KAMIS 부류
#   role       : 이 재료가 수업에서 맡는 자리 — 리포트에서 묶어 볼 때 쓴다
#   why        : 왜 골랐는지. 리포트 "데이터 설명" 절에 그대로 들어간다
BASKET = [
    {
        "key": "baechu", "name": ["배추"], "category": "채소류", "role": "국·김치",
        "why": "요리교실 5개 지역 전부에 들어가는 유일한 재료. 김장철 계절성이 가장 뚜렷할 것으로 보고 기준 품목으로 삼았다.",
    },
    {
        "key": "hobak", "name": ["애호박", "호박"], "category": "채소류", "role": "볶음",
        "why": "값이 작아 무시하기 쉽지만 12인 수업에서는 누적된다. 여름·가을 작황에 민감해 노이즈가 큰 품목으로 예상했다.",
    },
    {
        "key": "kongnamul", "name": ["콩나물"], "category": "채소류", "role": "국물",
        "why": "실내 재배라 날씨 영향이 적다. 계절성이 강한 품목들과 대조하기 위한 '대조군'으로 넣었다.",
    },
    {
        "key": "gamja", "name": ["감자"], "category": "식량작물", "role": "면·밥",
        "why": "저장이 가능한 작물. 수확기와 가격 저점이 어긋나는지 보려고 골랐다.",
    },
    {
        "key": "goguma", "name": ["고구마"], "category": "식량작물", "role": "간식",
        "why": "감자와 같은 저장 작물이라 두 품목의 움직임이 닮았는지 비교한다.",
    },
    {
        "key": "mu", "name": ["무"], "category": "채소류", "role": "국물",
        "why": "배추와 함께 김장 수요를 받는 품목. 배추와 같은 시기에 오르는지 확인한다.",
    },
    {
        "key": "daepa", "name": ["대파", "파"], "category": "채소류", "role": "양념",
        "why": "거의 모든 메뉴에 들어가는 공통 재료. 값이 크게 튀면 전 회차 원가에 영향을 준다.",
    },
    {
        "key": "sigeumchi", "name": ["시금치"], "category": "채소류", "role": "나물",
        "why": "겨울이 제철로 알려진 채소. '제철=저렴'이 맞는지 검증할 대표 사례로 골랐다.",
    },
    {
        "key": "oi", "name": ["오이"], "category": "채소류", "role": "반찬",
        "why": "여름이 제철인 채소. 시금치와 정반대 계절성이 나오는지 확인해 짝으로 본다.",
    },
]

# 부류 이름 → KAMIS 부류 코드. 이건 공식 문서에 고정으로 나와 있는 값이다.
CATEGORY_CODES = {
    "식량작물": "100",
    "채소류": "200",
    "특용작물": "300",
    "과일류": "400",
    "축산물": "500",
    "수산물": "600",
}


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


def summary_lines() -> list[str]:
    """CLI 에 보여줄 요약. 리포트에 붙일 표의 원본이기도 하다."""
    lines = ["번호  키          품목        부류        수업에서 맡는 자리"]
    lines.append("-" * 62)
    for i, item in enumerate(BASKET, 1):
        lines.append(
            f"{i:>2}.  {item['key']:<10}  {item['name'][0]:<8}  "
            f"{item['category']:<8}  {item['role']}"
        )
    return lines
