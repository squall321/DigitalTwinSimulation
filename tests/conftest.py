# Track B 테스트 공용 픽스처: 단일 요소 합성 메쉬와 실파일 최소 파서.
import pytest

from dyna_io.classify import classify_solid
from dyna_io.model import ElementType, MeshData, ShellElement, SolidElement

EX01 = "/data/ball_drop_test_v3/ex01_hex8_m027_baseline/ex01_hex8_m027_baseline.k"
EX02 = "/data/ball_drop_test_v3/ex02_tet4_m027_baseline/ex02_tet4_m027_baseline.k"


def _parse_min(path):
    """Track A의 parser 부재 시에도 Track B 회귀가 돌도록 한 최소 파서.

    *NODE(16칸 고정폭) + *ELEMENT_SOLID(자유 split)만 읽는다.
    """
    nodes = {}
    solids = []
    mode = None
    with open(path) as f:
        for line in f:
            s = line.rstrip("\n")
            if s.startswith("*"):
                up = s.upper()
                if up.startswith("*NODE"):
                    mode = "node"
                elif up.startswith("*ELEMENT_SOLID"):
                    mode = "elem"
                else:
                    mode = None
                continue
            if not s.strip() or s.lstrip().startswith("$"):
                continue
            if mode == "node":
                nid = int(s[0:8])
                nodes[nid] = (float(s[8:24]), float(s[24:40]), float(s[40:56]))
            elif mode == "elem":
                p = s.split()
                n8 = [int(v) for v in p[2:10]]
                solids.append(SolidElement(int(p[0]), int(p[1]), n8, classify_solid(n8)))
    return MeshData(nodes=nodes, solids=solids, src_path=path)


@pytest.fixture
def hex8_mesh():
    nodes = {1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0),
             5: (0, 0, 1), 6: (1, 0, 1), 7: (1, 1, 1), 8: (0, 1, 1)}
    el = SolidElement(1, 1, [1, 2, 3, 4, 5, 6, 7, 8], ElementType.HEX8)
    return MeshData(nodes=nodes, solids=[el])


@pytest.fixture
def tet4_mesh():
    """8슬롯 degenerate 저장(마지막 노드 반복)."""
    nodes = {1: (0, 0, 0), 2: (1, 0, 0), 3: (0, 1, 0), 4: (0, 0, 1)}
    el = SolidElement(1, 1, [1, 2, 3, 4, 4, 4, 4, 4], ElementType.TET4)
    return MeshData(nodes=nodes, solids=[el])


@pytest.fixture
def wedge6_mesh():
    nodes = {1: (0, 0, 0), 2: (1, 0, 0), 3: (0, 1, 0),
             4: (0, 0, 1), 5: (1, 0, 1), 6: (0, 1, 1)}
    el = SolidElement(1, 1, [1, 2, 3, 4, 5, 6, 6, 6], ElementType.WEDGE6)
    return MeshData(nodes=nodes, solids=[el])


@pytest.fixture
def pyramid5_mesh():
    nodes = {1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0),
             5: (0.5, 0.5, 1)}
    el = SolidElement(1, 1, [1, 2, 3, 4, 5, 5, 5, 5], ElementType.PYRAMID5)
    return MeshData(nodes=nodes, solids=[el])


@pytest.fixture
def quad_shell_mesh():
    nodes = {1: (0, 0, 0), 2: (1, 0, 0), 3: (1, 1, 0), 4: (0, 1, 0)}
    el = ShellElement(1, 9, [1, 2, 3, 4], ElementType.QUAD4)
    return MeshData(nodes=nodes, shells=[el])


@pytest.fixture(scope="session")
def ex01_mesh():
    import os
    if not os.path.exists(EX01):
        pytest.skip("ex01 실파일 없음")
    return _parse_min(EX01)


@pytest.fixture(scope="session")
def ex02_mesh():
    import os
    if not os.path.exists(EX02):
        pytest.skip("ex02 실파일 없음")
    return _parse_min(EX02)
