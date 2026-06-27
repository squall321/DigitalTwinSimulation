# build_surface 삼각분할·외향 일관·셸 병합과 STL 라이터/watertight 진단 검증.
import struct

import numpy as np

from dyna_io.stl import _tri_normals, watertight_diag, write_stl
from dyna_io.surface import build_surface


def _outward_consistent(verts, tris):
    V = np.asarray(verts, dtype=float)
    N = _tri_normals(V, np.array(tris))
    C = V.mean(0)
    fc = np.array([V[list(t)].mean(0) for t in tris])
    return bool((np.einsum("ij,ij->i", N, fc - C) > 1e-9).all())


def test_hex8_surface_watertight(hex8_mesh):
    tris, used, diag = build_surface(hex8_mesh)
    assert len(tris) == 12
    assert diag["watertight"]
    assert watertight_diag(tris)["watertight"]
    verts = [hex8_mesh.nodes[n] for n in used]
    assert _outward_consistent(verts, tris)


def test_tet4_surface(tet4_mesh):
    tris, used, diag = build_surface(tet4_mesh)
    assert len(tris) == 4
    assert diag["watertight"]
    assert _outward_consistent([tet4_mesh.nodes[n] for n in used], tris)


def test_wedge6_surface(wedge6_mesh):
    tris, used, diag = build_surface(wedge6_mesh)
    assert len(tris) == 8  # 삼각 2 + quad 3 -> 2tri*3
    assert diag["watertight"]
    assert _outward_consistent([wedge6_mesh.nodes[n] for n in used], tris)


def test_pyramid5_surface(pyramid5_mesh):
    tris, used, diag = build_surface(pyramid5_mesh)
    assert len(tris) == 6  # base quad->2tri + 4 tri
    assert diag["watertight"]
    assert _outward_consistent([pyramid5_mesh.nodes[n] for n in used], tris)


def test_shell_merge(quad_shell_mesh):
    tris, used, diag = build_surface(quad_shell_mesh, merge_shells=True)
    assert len(tris) == 2
    assert diag["n_shell_tris"] == 2


def test_shell_not_merged(quad_shell_mesh):
    tris, _, diag = build_surface(quad_shell_mesh, merge_shells=False)
    assert tris == []


def test_used_nids_index_space(hex8_mesh):
    tris, used, _ = build_surface(hex8_mesh)
    # 모든 인덱스가 used 범위 안.
    for t in tris:
        for i in t:
            assert 0 <= i < len(used)


def test_parts_filter(ex02_mesh):
    # PID3(hex)만 추출하면 그 part의 외곽만.
    tris, used, diag = build_surface(ex02_mesh, parts=[3])
    assert diag["n_boundary_faces"] == 64
    assert len(tris) == 128


def test_write_binary_stl(hex8_mesh, tmp_path):
    tris, used, _ = build_surface(hex8_mesh)
    verts = [hex8_mesh.nodes[n] for n in used]
    out = tmp_path / "hex.stl"
    write_stl(str(out), verts, tris, binary=True)
    data = out.read_bytes()
    assert len(data) == 84 + len(tris) * 50  # 80헤더 + 4카운트 + 50/tri
    n = struct.unpack("<I", data[80:84])[0]
    assert n == len(tris)


def test_write_ascii_stl(hex8_mesh, tmp_path):
    tris, used, _ = build_surface(hex8_mesh)
    verts = [hex8_mesh.nodes[n] for n in used]
    out = tmp_path / "hex_ascii.stl"
    write_stl(str(out), verts, tris, binary=False)
    txt = out.read_text()
    assert txt.startswith("solid")
    assert txt.rstrip().endswith("endsolid dts")
    assert txt.count("facet normal") == len(tris)


def test_watertight_diag_open_surface(quad_shell_mesh):
    tris, _, _ = build_surface(quad_shell_mesh)
    wd = watertight_diag(tris)
    assert not wd["watertight"]
    assert wd["boundary_edges"] == 4  # 단일 quad 경계 4에지


def test_real_files_produce_surface(ex01_mesh, ex02_mesh):
    for mesh in (ex01_mesh, ex02_mesh):
        tris, used, diag = build_surface(mesh)
        assert len(tris) > 0
        assert len(used) > 0
        assert diag["n_boundary_faces"] > 0
