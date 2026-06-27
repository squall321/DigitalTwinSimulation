# solid_faces 면 수·degenerate 환원, extract_free_faces 해싱, orient_outward 외향 판정 검증.
import numpy as np

from dyna_io.faces import (
    extract_free_faces,
    orient_outward,
    solid_faces,
    _face_normal,
)
from dyna_io.model import ElementType, SolidElement


def test_hex8_six_faces(hex8_mesh):
    el = hex8_mesh.solids[0]
    faces = solid_faces(el)
    assert len(faces) == 6
    assert all(len(f) == 4 for f in faces)


def test_tet4_four_tri_faces(tet4_mesh):
    el = tet4_mesh.solids[0]
    faces = solid_faces(el)
    assert len(faces) == 4
    assert all(len(f) == 3 for f in faces)


def test_wedge6_faces(wedge6_mesh):
    faces = solid_faces(wedge6_mesh.solids[0])
    sizes = sorted(len(f) for f in faces)
    assert sizes == [3, 3, 4, 4, 4]  # 삼각 2 + 측면 quad 3


def test_pyramid5_faces(pyramid5_mesh):
    faces = solid_faces(pyramid5_mesh.solids[0])
    sizes = sorted(len(f) for f in faces)
    assert sizes == [3, 3, 3, 3, 4]  # base quad + 측면 tri 4


def test_degenerate_collapse_returns_no_faces_for_malformed():
    # 고유 7노드(비표준 collapse)는 면 추출 불가로 진단(크래시 금지).
    el = SolidElement(1, 1, [1, 2, 3, 4, 5, 6, 7, 5], ElementType.HEX8)
    assert solid_faces(el) == []


def test_extract_free_faces_single_hex(hex8_mesh):
    free, diag = extract_free_faces(hex8_mesh.solids, hex8_mesh.nodes)
    assert len(free) == 6  # 단일 hex의 모든 면이 자유면
    assert diag["non_conformal_faces"] == 0


def test_extract_free_faces_two_shared_hex():
    # 두 hex가 한 면을 공유 → 그 면은 자유면 아님(자유면 10개).
    nodes = {i: c for i, c in enumerate([
        (0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0),
        (0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1),
        (0, 0, 2), (1, 0, 2), (1, 1, 2), (0, 1, 2)], start=1)}
    e1 = SolidElement(1, 1, [1, 2, 3, 4, 5, 6, 7, 8], ElementType.HEX8)
    e2 = SolidElement(2, 1, [5, 6, 7, 8, 9, 10, 11, 12], ElementType.HEX8)
    free, diag = extract_free_faces([e1, e2], nodes)
    assert len(free) == 10  # 12면 중 공유면 2개 상쇄
    assert diag["non_conformal_faces"] == 0


def test_orient_outward_bottom_face(hex8_mesh):
    el = hex8_mesh.solids[0]
    nodes = hex8_mesh.nodes
    # 바닥면(z=0)을 외향 정렬 → 법선이 -z 여야 함
    bottom = (1, 4, 3, 2)
    o = orient_outward(bottom, el, nodes)
    n = _face_normal(np.array([nodes[x] for x in o]))
    assert n[2] < -0.9


def test_orient_outward_all_outward(hex8_mesh):
    el = hex8_mesh.solids[0]
    nodes = hex8_mesh.nodes
    C = np.mean(list(nodes.values()), axis=0)
    for f in solid_faces(el):
        o = orient_outward(f, el, nodes)
        P = np.array([nodes[x] for x in o])
        n = _face_normal(P)
        assert np.dot(n, P.mean(0) - C) > 0  # 외향
