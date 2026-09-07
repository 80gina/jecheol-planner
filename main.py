"""제철밥상 플래너 — 지역별 제철 식재료·가격·맞춤 요리 추천 CLI.

    python main.py probe --date 2026-08-26        # KAMIS 응답 구조 확인 (개발용)
    python main.py ingredient                     # 뉴스에서 제철 식재료·지역 추출
    python main.py price --category 채소류         # 지역별 가격 수집
    python main.py menu --people 12               # 지역 맞춤 요리 추천
    python main.py plan --sessions 4              # 요리교실 식단표 + 장보기 목록
    python main.py dashboard                      # HTML 대시보드
    python main.py card --menu "전어무침"          # 순자 할머니 레시피 카드
"""

from __future__ import annotations

import argparse
import sys
from datetime import date

import config


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python main.py",
        description="제철밥상 플래너 — 지역별 제철 식재료·가격·맞춤 요리 추천",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("--log-level", default="INFO",
                   choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    sub = p.add_subparsers(dest="command", metavar="<명령>")

    pr = sub.add_parser("probe", help="KAMIS 응답 구조를 확인한다 (개발용)")
    pr.add_argument("--date", default=date.today().isoformat(),
                    help="조회 날짜 YYYY-MM-DD (기본: 오늘)")
    pr.add_argument("--category", default="채소류",
                    choices=["식량작물", "채소류", "특용작물", "과일류", "축산물", "수산물"])
    pr.add_argument("--cls", default="01", choices=["01", "02"],
                    help="01=소매, 02=도매 (기본: 01)")
    pr.add_argument("--country", default="", help="지역 코드 (생략 가능)")

    sub.add_parser("ingredient", help="뉴스에서 제철 식재료·지역을 뽑는다")
    sub.add_parser("price", help="지역별 식재료 가격을 수집한다")
    sub.add_parser("menu", help="지역 맞춤 요리를 추천한다")
    sub.add_parser("plan", help="요리교실 식단표·장보기 목록을 만든다")
    sub.add_parser("dashboard", help="HTML 대시보드를 만든다")
    sub.add_parser("card", help="순자 할머니 레시피 카드를 만든다")

    return p


def cmd_probe(args, cfg: dict, log) -> int:
    """KAMIS 키가 통하는지, 응답이 어떤 모양인지 눈으로 확인한다."""
    import kamis

    try:
        cert_key = config.get_key("KAMIS_CERT_KEY")
        cert_id = config.get_key("KAMIS_CERT_ID")
    except config.ConfigError as e:
        log.error("%s", e)
        return 2

    log.info("KAMIS 인증키: %s / 아이디: %s",
             config.mask(cert_key), config.mask(cert_id))

    try:
        payload = kamis.probe(cfg, log, cert_key, cert_id,
                              args.date, args.category, args.country, args.cls)
    except kamis.KamisError as e:
        log.error("조회 실패: %s", e)
        return 3

    out = config.resolve_path(cfg, "output_dir").parent / "output"
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

    if args.command == "probe":
        return cmd_probe(args, cfg, log)

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
