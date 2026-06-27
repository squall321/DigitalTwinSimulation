# outer_boundary가 비conformal 내부 가짜면을 제외하고 외부 셸만 남기는지 검증.
from dyna_io.boundary import outer_boundary
from dyna_io.faces import extract_free_faces


def test_single_hex_all_boundary(hex8_mesh):
    free, _ = extract_free_faces(hex8_mesh.solids, hex8_mesh.nodes)
    bnd, nids = outer_boundary(free, hex8_mesh.nodes, solids=hex8_mesh.solids)
    assert len(bnd) == 6           # 단일 hex는 모든 면이 외부
    assert nids == set(range(1, 9))


def test_single_tet_all_boundary(tet4_mesh):
    free, _ = extract_free_faces(tet4_mesh.solids, tet4_mesh.nodes)
    bnd, nids = outer_boundary(free, tet4_mesh.nodes, solids=tet4_mesh.solids)
    assert len(bnd) == 4
    assert nids == {1, 2, 3, 4}


def test_ex01_removes_internal_interfaces(ex01_mesh):
    # 비conformal part 인터페이스(PID1↔2↔3)는 자유면이지만 외부가 아님 → 제외.
    free, _ = extract_free_faces(ex01_mesh.solids, ex01_mesh.nodes)
    bnd, nids = outer_boundary(free, ex01_mesh.nodes, solids=ex01_mesh.solids)
    assert len(free) == 920
    assert len(bnd) < len(free)    # 내부 인터페이스가 제거됨
    assert len(bnd) == 780


def test_ex02_tet_block_outer_shell(ex02_mesh):
    # 실측: tet PID2 단독 자유면 9600개 중 진짜 외곽 1040개.
    tets = [e for e in ex02_mesh.solids if e.pid == 2]
    free, _ = extract_free_faces(tets, ex02_mesh.nodes)
    assert len(free) == 9600
    bnd, _ = outer_boundary(free, ex02_mesh.nodes, solids=tets)
    assert len(bnd) == 1040        # 비conformal 가짜면 8560개 제외


def test_ex02_full_assembly(ex02_mesh):
    free, _ = extract_free_faces(ex02_mesh.solids, ex02_mesh.nodes)
    bnd, _ = outer_boundary(free, ex02_mesh.nodes, solids=ex02_mesh.solids)
    assert len(free) == 10000
    assert len(bnd) == 1200        # part 인터페이스까지 제거된 외부 셸
