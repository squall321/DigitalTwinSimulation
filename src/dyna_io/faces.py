# 솔리드 요소의 면 추출·자유면 판정·외향 정렬. winding은 표를 믿지 않고 반대편 노드로 강제.
import numpy as np

from dyna_io.model import SolidElement

# 면-노드 매핑표. 인덱스는 '순서보존 고유 노드' 리스트(u)의 위치.
# 각 면은 바깥에서 본 CCW 순서로 정의(이후 orient_outward가 최종 외향 강제).
#
# TET4: u = [0,1,2,3]
_TET4_FACES = [
    (0, 2, 1),
    (0, 1, 3),
    (1, 2, 3),
    (2, 0, 3),
]
# PYRAMID5: u = [base0,base1,base2,base3, apex4]
_PYRAMID5_FACES = [
    (0, 3, 2, 1),  # base quad
    (0, 1, 4),
    (1, 2, 4),
    (2, 3, 4),
    (3, 0, 4),
]
# WEDGE6 (triangular prism): u = [t0,t1,t2 (bottom tri), t3,t4,t5 (top tri)]
# LS-DYNA degenerate-hex wedge 규약: 하단 삼각형(0,1,2) / 상단 삼각형(3,4,5),
# 측면 quad는 (0,1)-(3,4), (1,2)-(4,5), (2,0)-(5,3).
_WEDGE6_FACES = [
    (0, 2, 1),        # bottom tri
    (3, 4, 5),        # top tri
    (0, 1, 4, 3),     # side quad
    (1, 2, 5, 4),     # side quad
    (2, 0, 3, 5),     # side quad
]
# HEX8: u = [0..7], LS-DYNA 표준 노드 순서(하단 0123, 상단 4567).
_HEX8_FACES = [
    (0, 3, 2, 1),  # bottom
    (4, 5, 6, 7),  # top
    (0, 1, 5, 4),  # side
    (1, 2, 6, 5),  # side
    (2, 3, 7, 6),  # side
    (3, 0, 4, 7),  # side
]

# 고유 노드 수 -> 면 표. etype을 믿지 않고 실제 geometry(고유노드수)로 표를 고른다
# → degenerate hex가 8슬롯이지만 고유 4/5/6개면 자동으로 올바른 표 선택(IndexError 방지).
_FACE_TABLE_BY_NUNIQUE = {
    4: _TET4_FACES,
    5: _PYRAMID5_FACES,
    6: _WEDGE6_FACES,
    8: _HEX8_FACES,
}


def _dedup_face(idx_tuple, u):
    """면을 실제 NID로 매핑하고, collapse된 인접 중복 노드를 제거.

    degenerate hex가 부분적으로 collapse되면 quad가 같은 노드를 두 번 가질 수
    있다 → 인접(순환 포함) 중복을 줄여 tri로 환원, 면적 0 면은 None.
    """
    nids = [u[i] for i in idx_tuple]
    out = []
    for nid in nids:
        if not out or out[-1] != nid:
            out.append(nid)
    # 순환 경계(마지막==처음) 정리
    while len(out) > 1 and out[0] == out[-1]:
        out.pop()
    if len(out) < 3:
        return None
    return tuple(out)


def solid_faces(el: SolidElement) -> list:
    """요소의 면 목록을 NID 튜플로 반환(각 면 3 또는 4 노드).

    고유노드 기반. degenerate hex의 collapse된 quad는 tri로 환원(중복 면 방지).
    """
    u = list(dict.fromkeys(el.node_ids))  # 순서보존 고유 노드
    table = _FACE_TABLE_BY_NUNIQUE.get(len(u))  # etype 아닌 실제 고유노드수로 표 선택
    if table is None:
        return []  # 7개 등 비표준 collapse: 면 추출 불가(상위에서 진단)
    faces = []
    for idx_tuple in table:
        f = _dedup_face(idx_tuple, u)
        if f is not None:
            faces.append(f)
    return faces


def extract_free_faces(elements, nodes):
    """frozenset(노드) 해싱으로 1회 등장 면만 자유면으로 추출.

    returns (free, diag).
      free: list of (el, ordered_face_nodes) — 자유면(외향 정렬 전).
      diag: {"non_conformal_faces": k} — 3회 이상 등장한 면 수(비conformal 진단).
    """
    bucket = {}  # frozenset(노드) -> [(el, ordered)]
    for el in elements:
        for fn in solid_faces(el):
            bucket.setdefault(frozenset(fn), []).append((el, fn))
    free = [occ[0] for occ in bucket.values() if len(occ) == 1]
    n3plus = sum(1 for occ in bucket.values() if len(occ) >= 3)
    return free, {"non_conformal_faces": n3plus}


def orient_outward(face_nodes, el, nodes):
    """면을 외향(법선이 요소 바깥)으로 정렬해 반환.

    센트로이드가 아니라 '면에 없는 반대편 요소 노드'를 기준으로 판정한다
    (degenerate 요소에서 센트로이드는 불안정). 면 평면에서 반대편 노드가
    음의 쪽이면 외향이 맞고, 양의 쪽이면 뒤집는다.
    """
    fn = list(face_nodes)
    face_set = set(fn)
    # 면에 없는 요소 노드(반대편) 하나 선택
    opp = None
    for nid in el.node_ids:
        if nid not in face_set:
            opp = nid
            break
    if opp is None:
        return tuple(fn)  # 면이 요소 전체를 덮음(이상 케이스) → 그대로

    p = np.array([nodes[n] for n in fn], dtype=np.float64)
    # 면 법선(처음 세 점으로). degenerate 대비 면적 큰 삼각분할을 시도.
    normal = _face_normal(p)
    q = np.array(nodes[opp], dtype=np.float64)
    centroid = p.mean(axis=0)
    # 반대편 노드가 법선 방향(양수)에 있으면 법선이 안쪽을 향함 → 뒤집기
    if np.dot(normal, q - centroid) > 0:
        fn = fn[::-1]
    return tuple(fn)


def _face_normal(p):
    """폴리곤 정점 배열 p(M,3)의 법선. Newell 방법(비평면/degenerate 안정)."""
    n = np.zeros(3, dtype=np.float64)
    m = len(p)
    for i in range(m):
        a = p[i]
        b = p[(i + 1) % m]
        n[0] += (a[1] - b[1]) * (a[2] + b[2])
        n[1] += (a[2] - b[2]) * (a[0] + b[0])
        n[2] += (a[0] - b[0]) * (a[1] + b[1])
    norm = np.linalg.norm(n)
    if norm < 1e-30:
        return n
    return n / norm
