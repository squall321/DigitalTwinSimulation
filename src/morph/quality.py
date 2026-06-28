# 변형 메쉬 품질 게이트. invert는 절대부호가 아니라 '원본 대비 sign-flip'으로 판정.
import numpy as np

from dyna_io.model import ElementType

# HEX8 8개 적분점(±1/sqrt3)에서의 형상함수 자연좌표 미분 검사용 corner 좌표.
_HEX_GP = np.array(
    [[s, t, u] for s in (-1, 1) for t in (-1, 1) for u in (-1, 1)],
    dtype=np.float64,
) / np.sqrt(3.0)

# HEX8 LS-DYNA 노드 순서(하단 0123, 상단 4567)의 자연좌표.
_HEX_NAT = np.array(
    [[-1, -1, -1], [1, -1, -1], [1, 1, -1], [-1, 1, -1],
     [-1, -1, 1], [1, -1, 1], [1, 1, 1], [-1, 1, 1]],
    dtype=np.float64,
)


def _hex_jacobians(P):
    """HEX8 정점 P(8,3)의 8개 적분점에서 Jacobian 행렬식 (8,) 반환."""
    # dN/dxi 형상함수 미분: N_i = 1/8 (1+xi*xi_i)(1+eta*eta_i)(1+zeta*zeta_i)
    dets = np.empty(len(_HEX_GP), dtype=np.float64)
    for g, (xi, eta, zeta) in enumerate(_HEX_GP):
        dN = np.empty((8, 3), dtype=np.float64)
        for i in range(8):
            xi_i, eta_i, zeta_i = _HEX_NAT[i]
            dN[i, 0] = 0.125 * xi_i * (1 + eta * eta_i) * (1 + zeta * zeta_i)
            dN[i, 1] = 0.125 * (1 + xi * xi_i) * eta_i * (1 + zeta * zeta_i)
            dN[i, 2] = 0.125 * (1 + xi * xi_i) * (1 + eta * eta_i) * zeta_i
        J = dN.T @ P                                # (3,3)
        dets[g] = np.linalg.det(J)
    return dets


def _tet_jacobian(P):
    """TET4 정점 P(4,3)의 Jacobian 행렬식(상수). 부호=부피 6배."""
    return np.linalg.det(np.array([P[1] - P[0], P[2] - P[0], P[3] - P[0]]))


def _elem_min_jacobian(P, etype):
    """요소 타입별 최소 Jacobian. HEX는 8적분점 min, 그 외는 tet 분해 min."""
    if etype == ElementType.HEX8 and len(P) == 8:
        return float(_hex_jacobians(P).min())
    if etype == ElementType.TET4 and len(P) == 4:
        return _tet_jacobian(P)
    # PYRAMID5/WEDGE6/degenerate: corner tet 분해의 최소 부호 부피로 근사.
    n = len(P)
    if n < 4:
        return 0.0
    # 0번 정점 기준 fan 분해
    dets = []
    for i in range(1, n - 1):
        for j in range(i + 1, n):
            dets.append(np.linalg.det(
                np.array([P[i] - P[0], P[j] - P[0],
                          P[(i + j) % n] - P[0]])))
    return float(min(dets)) if dets else 0.0


def _aspect(P):
    """요소 aspect 근사 = 최장 엣지 / 최단 엣지(0거리 가드)."""
    n = len(P)
    edges = [np.linalg.norm(P[i] - P[j])
             for i in range(n) for j in range(i + 1, n)]
    edges = [e for e in edges if e > 1e-12]
    if not edges:
        return float("inf")
    return max(edges) / min(edges)


def check_quality(X, solids, X_orig):
    """변형 좌표 X의 솔리드 품질 점검.

    invert 판정: 원본 X_orig에서의 Jacobian 부호와 X에서의 부호가 다르면 뒤집힘.
    (원본이 음수 컨벤션일 수 있으므로 절대 부호가 아니라 sign-flip 사용 — DESIGN §7-5)

    Args:
      X: (N,3) 변형 좌표.
      solids: SolidElement 리스트. node_ids는 dense 행 인덱스(driver가 변환).
      X_orig: (N,3) 원본 좌표.

    Returns:
      {"min_jacobian": float, "inverted": [eid,...], "aspect_max": float}
        min_jacobian: 모든 요소·적분점에서의 최소 (현재) Jacobian.
        inverted: 원본 대비 부호가 뒤집힌 요소 eid 목록.
        aspect_max: 최대 aspect ratio.
    """
    X = np.asarray(X, dtype=np.float64).reshape(-1, 3)
    X_orig = np.asarray(X_orig, dtype=np.float64).reshape(-1, 3)

    min_jac = float("inf")
    aspect_max = 0.0
    inverted = []

    for el in solids:
        rows = list(dict.fromkeys(el.node_ids))    # 고유 행 인덱스
        Pn = X[rows]
        Po = X_orig[rows]
        jn = _elem_min_jacobian(Pn, el.etype)
        jo = _elem_min_jacobian(Po, el.etype)
        min_jac = min(min_jac, jn)
        aspect_max = max(aspect_max, _aspect(Pn))
        # 원본 대비 부호 반전(원본이 0이면 현재 부호로 판정)
        if jo != 0.0:
            if np.sign(jn) != np.sign(jo):
                inverted.append(el.eid)
        elif jn < 0:
            inverted.append(el.eid)

    if min_jac == float("inf"):
        min_jac = 0.0
    return {
        "min_jacobian": min_jac,
        "inverted": inverted,
        "aspect_max": aspect_max,
    }
