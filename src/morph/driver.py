# 편집 외곽 STL을 체적 메쉬에 전파하는 모핑 드라이버. 증분+품질게이트, 실패시 거부 우선.
from dataclasses import dataclass

import numpy as np
from scipy.spatial import cKDTree

from core.result import StageResult
from dyna_io.faces import extract_free_faces
from dyna_io.boundary import outer_boundary
from dyna_io.stl import read_stl_points
from morph.laplacian import morph_laplacian
from morph.quality import check_quality
from morph.rbf import morph_rbf

# RBF 경계노드 상한. 초과 시 O(B^3) 비용으로 거부(DESIGN §7-4).
_RBF_B_LIMIT = 4000


@dataclass
class _RowSolid:
    """quality/laplacian용: node_ids가 dense 행 인덱스인 솔리드 래퍼."""
    eid: int
    pid: int
    node_ids: list
    etype: object


def _boundary_displacement(X, bnd_rows, target_pts):
    """경계 노드를 편집외곽 STL 점구름에 cKDTree 되투영해 변위 계산.

    sidecar 인덱스 매핑은 STL 왕복 시 무효 → 항상 공간 매칭(DESIGN §4.4-2).
    각 경계 노드의 최근접 STL 점으로의 변위를 반환.
    """
    tree = cKDTree(target_pts)
    _, idx = tree.query(X[bnd_rows])
    return target_pts[idx] - X[bnd_rows]


def morph_phone_volume(mesh, edited_outer_stl, method="laplacian", scale=1.0,
                       n_steps=8, max_substeps=6):
    """편집 외곽 STL을 입력으로 체적 메쉬 노드를 전파 변형해 StageResult 반환.

    절차(DESIGN §4.4):
      1) dense_index 1회 생성, 외부 경계 노드 추출.
      2) 경계 노드 ↔ 편집외곽 STL 되투영으로 bnd_disp 계산(scale 적용).
      3) method=laplacian: 증분 적용, 매 스텝 변형메쉬에서 재조립(준-비선형).
         게이트 실패 스텝은 이분(max_substeps 한계).
      4) 한계 도달 시 기본은 거부(ok=False) + 변형축소 hint. RBF 폴백 아님.
         method=rbf: 회전/비연결 입력용 대안(증분 없이 1패스).
      5) 성공 시 new_coords dict 산출(rewrite는 호출자/export 단계가 수행).

    Returns:
      StageResult. 성공 시 artifacts={"new_coords": {nid->xyz}},
      diagnostics={min_jacobian, aspect_max, n_boundary_nodes, n_internal_nodes, ...}.
      실패 시 fail(min_jacobian=..., inverted=[...]) + message에 축소 hint.
    """
    X0, nid2row, row2nid = mesh.dense_index()
    n = X0.shape[0]

    free, _diag = extract_free_faces(mesh.solids, mesh.nodes)
    _bf, bnd_nids = outer_boundary(free, mesh.nodes, solids=mesh.solids)
    bnd_rows = np.array([nid2row[n_] for n_ in bnd_nids if n_ in nid2row], dtype=np.intp)

    n_internal = n - len(bnd_rows)
    base_diag = {
        "n_boundary_nodes": int(len(bnd_rows)),
        "n_internal_nodes": int(n_internal),
    }

    if len(bnd_rows) == 0:
        return StageResult.fail("외부 경계 노드를 찾지 못함(모핑 입력 없음).", **base_diag)

    target_pts = read_stl_points(edited_outer_stl)
    if len(target_pts) == 0:
        return StageResult.fail(f"편집 외곽 STL이 비었음: {edited_outer_stl}", **base_diag)

    # 전체 경계 변위(scale 적용)
    bnd_disp_full = scale * _boundary_displacement(X0, bnd_rows, target_pts)

    # 내부 노드 0개면 경계만 이동(no-op 단락, 검증 D2).
    if n_internal == 0:
        X = X0.copy()
        X[bnd_rows] += bnd_disp_full
        return _finalize(mesh, X0, X, row2nid, method, base_diag, scale)

    rsolids = [_RowSolid(el.eid, el.pid,
                         [nid2row[n_] for n_ in el.node_ids if n_ in nid2row],
                         el.etype)
               for el in mesh.solids]

    if method == "rbf":
        if len(bnd_rows) > _RBF_B_LIMIT:
            return StageResult.fail(
                f"RBF 경계노드 {len(bnd_rows)} > {_RBF_B_LIMIT} (O(B^3) 비용). "
                "경계 다운샘플 또는 laplacian 사용.", **base_diag)
        X = morph_rbf(X0, bnd_rows, bnd_disp_full)
        return _finalize(mesh, X0, X, row2nid, method, base_diag, scale,
                         rsolids=rsolids)

    # laplacian 증분: 매 스텝 변형메쉬에서 재조립(준-비선형, DESIGN §7-2).
    X = X0.copy()
    applied = 0.0                                   # 누적 적용 비율 [0,1]
    step_frac = 1.0 / n_steps
    substep_used = 0
    last_quality = None

    while applied < 1.0 - 1e-12:
        frac = min(step_frac, 1.0 - applied)
        accepted = False
        while True:
            step_disp = bnd_disp_full * frac
            X_try = morph_laplacian(X, rsolids, bnd_rows, step_disp)
            q = check_quality(X_try, rsolids, X0)
            if not q["inverted"] and q["min_jacobian"] > 0:
                X = X_try
                applied += frac
                last_quality = q
                accepted = True
                break
            # 게이트 실패 → 스텝 이분
            substep_used += 1
            frac *= 0.5
            if substep_used > max_substeps:
                break
        if not accepted:
            q = q if last_quality is None else last_quality
            inverted = check_quality(X_try, rsolids, X0)["inverted"]
            new_scale = round(scale * 0.5, 4)
            return StageResult.fail(
                f"요소 뒤집힘(압입 inversion). 변형을 줄이세요(scale={new_scale}). "
                "그래도 실패 시 그립을 완화하세요. RBF는 압입에 더 약합니다.",
                min_jacobian=float(check_quality(X_try, rsolids, X0)["min_jacobian"]),
                inverted=inverted,
                suggested_scale=new_scale,
                **base_diag,
            )

    base_diag.update({
        "min_jacobian": float(last_quality["min_jacobian"]),
        "aspect_max": float(last_quality["aspect_max"]),
        "substeps_used": substep_used,
    })
    new_coords = {row2nid[i]: tuple(X[i]) for i in range(n)}
    return StageResult.success(
        message=f"모핑 성공(min_jacobian={last_quality['min_jacobian']:.4g}).",
        artifacts={"new_coords": new_coords},
        diagnostics=base_diag,
    )


def _finalize(mesh, X0, X, row2nid, method, base_diag, scale, rsolids=None):
    """rbf/no-op 경로의 최종 품질 게이트 + 결과 봉투 생성."""
    if rsolids is None:
        rsolids = [_RowSolid(el.eid, el.pid,
                             list(range(len(el.node_ids))), el.etype)
                   for el in mesh.solids]
    q = check_quality(X, rsolids, X0)
    base_diag.update({
        "min_jacobian": float(q["min_jacobian"]),
        "aspect_max": float(q["aspect_max"]),
    })
    if q["inverted"] or q["min_jacobian"] <= 0:
        new_scale = round(scale * 0.5, 4)
        return StageResult.fail(
            f"요소 뒤집힘. 변형을 줄이세요(scale={new_scale}).",
            inverted=q["inverted"], suggested_scale=new_scale, **base_diag)
    new_coords = {row2nid[i]: tuple(X[i]) for i in range(X.shape[0])}
    return StageResult.success(
        message=f"모핑 성공({method}, min_jacobian={q['min_jacobian']:.4g}).",
        artifacts={"new_coords": new_coords},
        diagnostics=base_diag,
    )
