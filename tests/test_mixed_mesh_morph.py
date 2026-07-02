# 혼합 메쉬(솔리드+셸) 모핑 회귀 테스트. 셸 전용 노드가 Laplacian을 특이행렬로 만들던 버그 방지.
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dyna_io.model import MeshData, SolidElement, ShellElement, ElementType  # noqa: E402


def _mixed_mesh():
    """솔리드 hex 1개 + 그 위에 얹힌 셸(솔리드에 없는 노드 참조)."""
    m = MeshData()
    # 솔리드 hex 노드 1~8
    coords = [(0, 0, 0), (10, 0, 0), (10, 10, 0), (0, 10, 0),
              (0, 0, 10), (10, 0, 10), (10, 10, 10), (0, 10, 10)]
    for i, c in enumerate(coords, start=1):
        m.nodes[i] = c
    m.solids.append(SolidElement(1, 1, list(range(1, 9)), ElementType.HEX8))
    # 셸: 노드 9~12 (솔리드에 없는 전용 노드)
    for i, c in enumerate([(0, 0, 20), (10, 0, 20), (10, 10, 20), (0, 10, 20)], start=9):
        m.nodes[i] = c
    m.shells.append(ShellElement(1, 2, [9, 10, 11, 12], ElementType.QUAD4))
    return m


def test_dense_index_solids_only_excludes_shell_nodes():
    """solids_only=True면 셸 전용 노드(9~12)를 제외한다."""
    m = _mixed_mesh()
    X_all, _, row_all = m.dense_index()
    X_solid, _, row_solid = m.dense_index(solids_only=True)

    assert set(row_all) == set(range(1, 13))        # 전체: 솔리드+셸
    assert set(row_solid) == set(range(1, 9))       # 솔리드만: 셸 노드 제외
    assert 9 not in row_solid and 12 not in row_solid


def test_default_dense_index_includes_shells():
    """기본(solids_only=False)은 기존대로 셸 노드 포함(하위호환)."""
    m = _mixed_mesh()
    _, _, row = m.dense_index()
    assert 9 in row and 12 in row
