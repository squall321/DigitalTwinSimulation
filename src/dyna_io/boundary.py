# 비conformal 메쉬에서 진짜 외부 표면만 추출. 자유면의 외향 쪽에 솔리드가 있으면 내부 가짜면으로 제외.
import numpy as np
from scipy.spatial import cKDTree

from dyna_io.model import ElementType
from dyna_io.faces import _face_normal, orient_outward

# 각 솔리드 요소를 tet으로 분해하는 표(고유 노드 리스트 u 인덱스 기준).
# point-in-element 판정을 element-type 무관하게 만들기 위함.
_TET_DECOMP = {
    ElementType.TET4: [(0, 1, 2, 3)],
    ElementType.PYRAMID5: [(0, 1, 2, 4), (0, 2, 3, 4)],
    ElementType.WEDGE6: [(0, 1, 2, 3), (1, 2, 3, 4), (2, 3, 4, 5)],
    ElementType.HEX8: [(0, 1, 3, 4), (1, 2, 3, 6), (1, 3, 4, 6), (1, 4, 5, 6), (3, 4, 6, 7)],
}

# 자유면 외향으로 내보내는 탐침 거리(면 자체 최소변 길이의 비율). 작게 잡아야
# 얇은 피처를 건너뛰지 않는다(실측: pf<=0.05에서 ex01/ex02 결과 안정).
_PROBE_FRAC = 0.02


def _element_tets(solids, nodes):
    """모든 솔리드를 tet으로 분해한 (M,4,3) 배열 반환."""
    tets = []
    for el in solids:
        u = list(dict.fromkeys(el.node_ids))
        V = [np.asarray(nodes[n], dtype=np.float64) for n in u]
        for t in _TET_DECOMP.get(el.etype, []):
            if max(t) < len(u):
                tets.append([V[i] for i in t])
    if not tets:
        return np.empty((0, 4, 3), dtype=np.float64)
    return np.asarray(tets, dtype=np.float64)


def outer_boundary(free_faces, nodes, solids=None):
    """자유면 중 외부 표면(외향 쪽에 솔리드 없음)만 반환.

    tet 비conformal 메쉬는 내부에 떠 있는 가짜 자유면을 만든다(실측: ex02 자유면
    10000개 중 외부 ~1200). 각 자유면 센트로이드에서 외향 법선으로 소량 탐침해
    그 점이 어떤 솔리드 내부에도 들지 않으면 외부 면으로 채택한다.

    Args:
      free_faces: list of (el, ordered_face_nodes). extract_free_faces 결과.
      nodes: NID -> (x,y,z).
      solids: 전체 솔리드 리스트. None이면 free_faces의 요소들로 대체(탐침 대상 축소
              → 정확도↓). 가능하면 전체 솔리드를 넘길 것.

    Returns:
      (boundary_faces, boundary_nids)
        boundary_faces: list of 외향 정렬된 면 노드 튜플.
        boundary_nids: 그 면들이 참조하는 NID 집합.
    """
    if not free_faces:
        return [], set()

    if solids is None:
        solids = list({id(el): el for el, _ in free_faces}.values())

    tets = _element_tets(solids, nodes)
    if len(tets) == 0:
        # 솔리드 분해 불가(셸-only 등) → 모든 자유면을 외향 정렬해 그대로 반환.
        oriented = [orient_outward(fn, el, nodes) for el, fn in free_faces]
        nids = {n for f in oriented for n in f}
        return oriented, nids

    A = tets[:, 0, :]                                  # (M,3)
    M = np.transpose(tets[:, 1:, :] - A[:, None, :], (0, 2, 1))  # (M,3,3)
    Minv = np.linalg.inv(M)
    tcent = tets.mean(axis=1)                          # (M,3)
    trad = np.linalg.norm(tets - tcent[:, None, :], axis=2).max(axis=1)
    tree = cKDTree(tcent)
    maxrad = float(trad.max())

    oriented = []
    probes = []
    for el, fn in free_faces:
        o = orient_outward(fn, el, nodes)
        oriented.append((el, o))
        Q = np.array([nodes[n] for n in o], dtype=np.float64)
        c = Q.mean(axis=0)
        nrm = _face_normal(Q)
        m = len(o)
        size = min(np.linalg.norm(Q[i] - Q[(i + 1) % m]) for i in range(m))
        probes.append(c + _PROBE_FRAC * size * nrm)
    probes = np.asarray(probes, dtype=np.float64)

    cand = tree.query_ball_point(probes, r=maxrad)
    boundary = []
    for i, (el, o) in enumerate(oriented):
        cl = cand[i]
        inside = False
        if cl:
            cl = np.asarray(cl, dtype=np.intp)
            d = probes[i] - A[cl]                       # (k,3)
            bc = np.einsum("kij,kj->ki", Minv[cl], d)   # (k,3) = l1,l2,l3
            l0 = 1.0 - bc.sum(axis=1)
            mins = np.minimum(l0, bc.min(axis=1))
            if (mins >= -1e-9).any():
                inside = True
        if not inside:
            boundary.append(o)

    nids = {n for f in boundary for n in f}
    return boundary, nids
