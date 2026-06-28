# 전체 파이프라인 배치 CLI: 폰 .k → 그립 → 모핑 → 솔리드 .k 를 1커맨드로.
import argparse
import sys
import tempfile

from app.session import GripState
from app import pipeline


def main():
    p = argparse.ArgumentParser(
        prog="dts-pipeline",
        description="폰 .k → 손 그립 → 외곽 모핑 → 재해석 가능한 솔리드 .k (end-to-end).")
    p.add_argument("k_file", help="입력 폰 .k 경로")
    p.add_argument("out_k", help="출력 모핑 .k 경로")
    p.add_argument("--style", default="natural", choices=["natural", "tight"],
                   help="그립 스타일")
    p.add_argument("--handedness", default="right", choices=["left", "right"])
    p.add_argument("--method", default="laplacian", choices=["laplacian", "rbf"])
    p.add_argument("--scale", type=float, default=1.0, help="모핑 변형 배율")
    p.add_argument("--workdir", default=None, help="세션 작업 디렉토리(미지정 시 임시)")
    p.add_argument("--no-grip", action="store_true",
                   help="그립 생략(외곽을 그대로 모핑 입력으로 — 변형 없음 검증용)")
    args = p.parse_args()

    base = args.workdir or tempfile.mkdtemp(prefix="dts_")
    st = GripState.load_or_create("cli", base)

    steps = [("extract", lambda: pipeline.extract_surface(st, args.k_file))]
    if not args.no_grip:
        steps += [
            ("load_hand", lambda: pipeline.load_hand(st, args.handedness)),
            ("grip", lambda: pipeline.grip_phone(st, args.style)),
        ]
    steps += [
        ("morph", lambda: pipeline.morph_phone(st, method=args.method, scale=args.scale)),
        ("export", lambda: pipeline.export_solid_k(st, args.out_k)),
    ]

    for name, fn in steps:
        res = fn()
        status = "OK" if res.ok else "FAIL"
        print(f"[{status}] {name}: {res.message}")
        if not res.ok:
            print(f"  진단: {res.diagnostics}", file=sys.stderr)
            sys.exit(1)
    print(f"\n완료 → {args.out_k}")


if __name__ == "__main__":
    main()
