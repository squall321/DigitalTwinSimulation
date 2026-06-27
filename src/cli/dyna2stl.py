# LS-DYNA .k → 외곽 표면 STL + boundary_nids.json 변환 배치 CLI (슬라이스1).
import argparse
import json
import os
import sys

from core.result import StageResult
from dyna_io.parser import parse_k_file
from dyna_io.stl import watertight_diag, write_stl
from dyna_io.surface import build_surface


def run(k_file: str, out_stl: str, parts=None, ascii_mode=False) -> StageResult:
    """파싱 → 외곽 표면화 → STL + boundary_nids.json 사이드카 기록.

    boundary_nids.json: {"src_k": 원본경로, "boundary_nids": [표면 NID...], "diag": {...}}.
    예측 가능한 도메인 실패(빈 표면)는 ok=False, IO 깨짐은 예외.
    """
    k_file = os.path.abspath(k_file)
    out_stl = os.path.abspath(out_stl)
    mesh = parse_k_file(k_file)

    tris, used_nids, diag = build_surface(mesh, parts=parts)
    if not tris:
        return StageResult.fail(
            "외곽 표면이 비어있음(요소/PART 필터 확인).",
            **diag,
        )

    verts = [mesh.nodes[n] for n in used_nids]
    write_stl(out_stl, verts, tris, binary=not ascii_mode)

    wt = watertight_diag(tris)
    # 사이드카는 STL 베이스명에 묶는다(같은 디렉토리에 여러 STL 출력 시 덮어쓰기 방지).
    stl_stem = os.path.splitext(os.path.basename(out_stl))[0]
    sidecar = os.path.join(os.path.dirname(out_stl), f"{stl_stem}.boundary_nids.json")
    with open(sidecar, "w") as f:
        json.dump(
            {
                "src_k": k_file,
                "boundary_nids": list(used_nids),
                "diag": {**diag, **wt},
            },
            f,
            indent=2,
        )

    return StageResult(
        ok=True,
        artifacts={"surface_stl": out_stl, "boundary_nids": sidecar, "src_k": k_file},
        diagnostics={**diag, **wt},
        message=f"표면 {len(tris)}삼각형 / 경계노드 {len(used_nids)}개 추출. watertight={wt['watertight']}",
    )


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="dyna2stl",
        description="LS-DYNA .k에서 외곽 표면 STL과 boundary_nids.json을 추출한다.",
    )
    ap.add_argument("k_file", help="입력 .k 파일 경로")
    ap.add_argument("out_stl", help="출력 STL 경로")
    ap.add_argument("--parts", type=int, nargs="+", default=None,
                    help="포함할 PART ID 목록(미지정 시 전체)")
    ap.add_argument("--ascii", action="store_true",
                    help="바이너리 대신 ASCII STL로 기록")
    args = ap.parse_args(argv)

    res = run(args.k_file, args.out_stl, parts=args.parts, ascii_mode=args.ascii)

    print(res.message)
    if res.ok:
        for name, path in res.artifacts.items():
            print(f"  {name}: {path}")
    return 0 if res.ok else 1


if __name__ == "__main__":
    sys.exit(main())
