# 슬라이스4: 폰 외곽 모핑(변위장 조화확장 + 품질게이트 + 거부동작) 검증.
import struct
import sys
from pathlib import Path

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dyna_io.parser import parse_k_file  # noqa: E402
from morph.driver import morph_phone_volume  # noqa: E402
from morph.quality import check_quality  # noqa: E402
from morph.laplacian import morph_laplacian  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))
from make_phone_k import make_phone_k  # noqa: E402


def _read_stl(p):
    with open(p, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        tris = []
        for _ in range(n):
            nrm = struct.unpack("<3f", f.read(12))
            vs = [struct.unpack("<3f", f.read(12)) for _ in range(3)]
            f.read(2)
            tris.append((nrm, vs))
    return tris


def _write_stl(p, tris):
    with open(p, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(tris)))
        for nrm, vs in tris:
            f.write(struct.pack("<3f", *nrm))
            for v in vs:
                f.write(struct.pack("<3f", *v))
            f.write(b"\0\0")


def _phone_and_outer(tmp_path):
    """합성 폰 .k + 외곽 STL 생성."""
    from dyna_io.surface import build_surface
    from dyna_io.stl import write_stl

    k = tmp_path / "phone.k"
    make_phone_k(str(k))
    mesh = parse_k_file(str(k))
    tris, used, _diag = build_surface(mesh)
    # tris는 build_surface의 used 인덱싱 → verts도 used 순서 (pipeline 버그 수정과 동일)
    verts = [tuple(mesh.nodes[nid]) for nid in used]
    stl = tmp_path / "outer.stl"
    write_stl(str(stl), verts, tris, binary=True)
    return mesh, stl


def _dent_stl(src_stl, dst_stl, z_thresh=7.5, dz=0.5):
    """STL 윗면(z>thresh)을 dz만큼 눌러 편집외곽 생성."""
    tris = _read_stl(src_stl)
    out = []
    for nrm, vs in tris:
        nv = [(x, y, z - dz if z > z_thresh else z) for (x, y, z) in vs]
        out.append((nrm, nv))
    _write_stl(dst_stl, out)


def test_morph_dent_succeeds(tmp_path):
    """폰 윗면 0.5mm 압입 → 모핑 성공, 노드수 보존, Jacobian>0."""
    mesh, outer = _phone_and_outer(tmp_path)
    edited = tmp_path / "edited.stl"
    _dent_stl(str(outer), str(edited), dz=0.5)

    res = morph_phone_volume(mesh, str(edited), method="laplacian", scale=1.0)
    assert res.ok, res.message
    assert res.diagnostics["min_jacobian"] > 0
    assert len(res.artifacts["new_coords"]) == len(mesh.nodes)
    assert res.diagnostics["n_internal_nodes"] > 0   # 내부 전파 일어남


def test_morph_excessive_dent_rejected(tmp_path):
    """폰 두께(8mm)의 과한 압입 → 거부(ok=False) + 축소 hint."""
    mesh, outer = _phone_and_outer(tmp_path)
    edited = tmp_path / "edited_big.stl"
    # 윗면을 7mm 눌러 두께를 거의 0으로 → inversion 유도
    _dent_stl(str(outer), str(edited), z_thresh=3.0, dz=7.5)

    res = morph_phone_volume(mesh, str(edited), method="laplacian", scale=1.0)
    assert not res.ok
    assert "scale" in res.message or "줄이" in res.message
    assert "suggested_scale" in res.diagnostics


def test_morph_preserves_node_count_via_rewrite(tmp_path):
    """rewrite_k 후 재파싱 시 노드수·요소수 동일."""
    from dyna_io.rewrite import rewrite_k

    mesh, outer = _phone_and_outer(tmp_path)
    edited = tmp_path / "edited.stl"
    _dent_stl(str(outer), str(edited), dz=0.3)
    res = morph_phone_volume(mesh, str(edited), scale=1.0)
    assert res.ok

    out_k = tmp_path / "morphed.k"
    rewrite_k(mesh, res.artifacts["new_coords"], str(out_k))
    mesh2 = parse_k_file(str(out_k))
    assert len(mesh2.nodes) == len(mesh.nodes)
    assert len(mesh2.solids) == len(mesh.solids)
    # 좌표가 실제로 바뀜
    changed = sum(1 for nid in mesh.nodes
                  if mesh.nodes[nid] != mesh2.nodes[nid])
    assert changed > 0


def test_quality_detects_inversion():
    """정상 hex Jacobian>0, 한 노드를 반대로 밀면 inverted 검출."""
    from dyna_io.model import ElementType

    class S:
        def __init__(s, nids):
            s.eid = 1
            s.pid = 1
            s.node_ids = nids
            s.etype = ElementType.HEX8

    X = np.array([
        [0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0],
        [0, 0, 1], [1, 0, 1], [1, 1, 1], [0, 1, 1],
    ], dtype=float)
    solids = [S(list(range(8)))]
    q = check_quality(X, solids, X)
    assert q["min_jacobian"] > 0
    assert not q["inverted"]

    # 노드 4를 반대편으로 밀어 뒤집기
    Xb = X.copy()
    Xb[4] = [0, 0, -2]
    qb = check_quality(Xb, solids, X)
    assert qb["inverted"]


def test_morph_no_internal_nodes_noop():
    """내부 노드 0개(단일 요소)면 경계만 이동, 예외 없음."""
    # 단일 hex: 8노드 전부 경계 → 내부 0개
    from dyna_io.model import MeshData, SolidElement, ElementType

    mesh = MeshData()
    for i, (x, y, z) in enumerate([
        (0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),
        (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10),
    ], start=1):
        mesh.nodes[i] = (x, y, z)
    mesh.solids.append(SolidElement(1, 1, list(range(1, 9)), ElementType.HEX8))
    X, nid2row, row2nid = mesh.dense_index()
    # 내부노드 0 → morph_laplacian no-op 경로 (직접 호출 스모크)
    bnd = np.arange(8, dtype=np.intp)
    disp = np.zeros((8, 3))

    class RS:
        eid = 1
        pid = 1
        node_ids = list(range(8))
        etype = ElementType.HEX8
    out = morph_laplacian(X, [RS()], bnd, disp)
    assert out.shape == X.shape
