# 솔리드 외부 자유면을 삼각형으로 분할하고 셸 요소를 직접 합쳐 외향 일관 표면을 만든다.
import numpy as np

from dyna_io.boundary import outer_boundary
from dyna_io.faces import _face_normal, extract_free_faces
from dyna_io.model import ElementType


def _triangulate(face_nodes):
    """3 또는 4 노드 면을 삼각형 리스트로. quad는 팬 분할(0,i,i+1)."""
    m = len(face_nodes)
    if m == 3:
        return [tuple(face_nodes)]
    if m == 4:
        a, b, c, d = face_nodes
        return [(a, b, c), (a, c, d)]
    # 일반 다각형(현 데이터엔 없음): 팬 분할
    return [(face_nodes[0], face_nodes[i], face_nodes[i + 1]) for i in range(1, m - 1)]


def _shell_outward(node_ids, nodes):
    """셸 면의 노드 순서를 그대로 두되 삼각분할만 반환. 셸은 원본 winding 신뢰."""
    u = list(dict.fromkeys(node_ids))
    return _triangulate(u)


def build_surface(mesh, parts=None, merge_shells=True):
    """체적 메쉬에서 외곽 표면 삼각형을 만든다.

    솔리드: 자유면 추출 → 외부 경계면만 선택 → 삼각형 분할(외향 정렬됨).
    셸: 원본 노드 순서로 삼각형 분할(merge_shells=True일 때 포함).

    Args:
      mesh: MeshData.
      parts: 포함할 PID 집합/리스트. None이면 전체.
      merge_shells: 셸 요소를 표면에 합칠지.

    Returns:
      (tris, used_nids, diag)
        tris: list of (i,j,k) — used_nids 위치를 가리키는 인덱스 삼각형.
        used_nids: row->NID 리스트(verts 구성용).
        diag: {"n_free_faces","non_conformal_faces","n_boundary_faces",
               "n_solid_tris","n_shell_tris","n_tris","watertight"}.
    """
    if parts is not None:
        parts = set(parts)
        solids = [el for el in mesh.solids if el.pid in parts]
        shells = [el for el in mesh.shells if el.pid in parts]
    else:
        solids = list(mesh.solids)
        shells = list(mesh.shells)

    nodes = mesh.nodes

    # --- 솔리드 자유면 → 외부 경계 → 삼각형 ---
    diag = {"n_free_faces": 0, "non_conformal_faces": 0, "n_boundary_faces": 0}
    solid_tris = []
    if solids:
        free, fdiag = extract_free_faces(solids, nodes)
        diag["n_free_faces"] = len(free)
        diag["non_conformal_faces"] = fdiag["non_conformal_faces"]
        boundary_faces, _bnids = outer_boundary(free, nodes, solids=solids)
        diag["n_boundary_faces"] = len(boundary_faces)
        for fn in boundary_faces:
            solid_tris.extend(_triangulate(fn))

    # --- 셸 직접 ---
    shell_tris = []
    if merge_shells and shells:
        for el in shells:
            shell_tris.extend(_shell_outward(el.node_ids, nodes))

    all_tris_nid = solid_tris + shell_tris

    # --- NID -> 컴팩트 인덱스 ---
    used = []
    seen = set()
    for tri in all_tris_nid:
        for nid in tri:
            if nid not in seen:
                seen.add(nid)
                used.append(nid)
    nid2row = {nid: i for i, nid in enumerate(used)}
    tris = [(nid2row[a], nid2row[b], nid2row[c]) for (a, b, c) in all_tris_nid]

    diag["n_solid_tris"] = len(solid_tris)
    diag["n_shell_tris"] = len(shell_tris)
    diag["n_tris"] = len(tris)
    diag["watertight"] = _is_watertight(tris)

    return tris, used, diag


def _is_watertight(tris):
    """모든 에지가 정확히 2개 삼각형에 공유되면 watertight."""
    if not tris:
        return False
    from collections import Counter

    ec = Counter()
    for a, b, c in tris:
        for e in ((a, b), (b, c), (c, a)):
            ec[frozenset(e)] += 1
    return all(v == 2 for v in ec.values())
