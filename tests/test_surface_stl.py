# 합성 큐브의 watertight 외곽 삼각형 수와 STL 바이너리/ASCII 라운드트립 검증.
import struct

import numpy as np

from dyna_io.model import ElementType, MeshData, SolidElement
from dyna_io.stl import watertight_diag, write_stl
from dyna_io.surface import build_surface


def _cube_2x2x2():
    """2x2x2 = 8 hex 큐브. 외곽 quad 24개 → 48 tri, watertight."""
    coord2nid = {}
    nodes = {}
    nxt = [0]

    def gn(x, y, z):
        key = (x, y, z)
        if key not in coord2nid:
            nxt[0] += 1
            coord2nid[key] = nxt[0]
            nodes[nxt[0]] = (float(x), float(y), float(z))
        return coord2nid[key]

    solids = []
    eid = 0
    for i in range(2):
        for j in range(2):
            for k in range(2):
                eid += 1
                n = [gn(i, j, k), gn(i + 1, j, k), gn(i + 1, j + 1, k), gn(i, j + 1, k),
                     gn(i, j, k + 1), gn(i + 1, j, k + 1), gn(i + 1, j + 1, k + 1), gn(i, j + 1, k + 1)]
                solids.append(SolidElement(eid, 1, n, ElementType.HEX8))
    return MeshData(nodes=nodes, solids=solids)


def _read_binary_stl(path):
    """바이너리 STL을 읽어 (정점배열(M,3,3), 법선(M,3)) 반환."""
    with open(path, "rb") as f:
        f.read(80)
        (n,) = struct.unpack("<I", f.read(4))
        tris = np.empty((n, 3, 3), dtype=np.float64)
        normals = np.empty((n, 3), dtype=np.float64)
        for i in range(n):
            vals = struct.unpack("<12f", f.read(48))
            f.read(2)  # attribute byte count
            normals[i] = vals[0:3]
            tris[i, 0] = vals[3:6]
            tris[i, 1] = vals[6:9]
            tris[i, 2] = vals[9:12]
    return tris, normals


def test_single_hex_cube_12_tris():
    nodes = {1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0),
             5: (0, 0, 1), 6: (1, 0, 1), 7: (1, 1, 1), 8: (0, 1, 1)}
    mesh = MeshData(nodes=nodes, solids=[SolidElement(1, 1, [1, 2, 3, 4, 5, 6, 7, 8], ElementType.HEX8)])
    tris, used, diag = build_surface(mesh)
    assert len(tris) == 12          # 6 quad → 12 tri
    assert diag["watertight"]
    assert watertight_diag(tris)["watertight"]


def test_2x2x2_cube_48_tris_watertight():
    mesh = _cube_2x2x2()
    tris, used, diag = build_surface(mesh)
    assert diag["n_boundary_faces"] == 24   # 외곽 quad
    assert len(tris) == 48                   # 24 quad → 48 tri
    assert diag["watertight"]
    assert watertight_diag(tris)["watertight"]


def test_binary_stl_roundtrip():
    mesh = _cube_2x2x2()
    tris, used, _ = build_surface(mesh)
    verts = np.array([mesh.nodes[n] for n in used], dtype=np.float64)

    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".stl")
    os.close(fd)
    try:
        write_stl(path, verts, tris, binary=True)
        rt_tris, rt_normals = _read_binary_stl(path)
        assert len(rt_tris) == len(tris)
        # 라운드트립 좌표가 원본 인덱스 삼각형과 일치.
        for i, (a, b, c) in enumerate(tris):
            assert np.allclose(rt_tris[i, 0], verts[a])
            assert np.allclose(rt_tris[i, 1], verts[b])
            assert np.allclose(rt_tris[i, 2], verts[c])
        # 저장된 법선이 winding과 일치(외향 정렬 전제 → 큐브 중심 기준 바깥).
        C = verts.mean(0)
        fc = rt_tris.mean(axis=1)
        assert (np.einsum("ij,ij->i", rt_normals, fc - C) > 0).all()
    finally:
        os.remove(path)


def test_ascii_stl_roundtrip_facet_count():
    mesh = _cube_2x2x2()
    tris, used, _ = build_surface(mesh)
    verts = [mesh.nodes[n] for n in used]

    import tempfile, os
    fd, path = tempfile.mkstemp(suffix=".stl")
    os.close(fd)
    try:
        write_stl(path, verts, tris, binary=False)
        txt = open(path).read()
        assert txt.startswith("solid")
        assert txt.rstrip().endswith("endsolid dts")
        assert txt.count("facet normal") == len(tris)
        assert txt.count("vertex") == 3 * len(tris)
    finally:
        os.remove(path)
