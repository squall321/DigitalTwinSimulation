# RBF가 회전 변형에서 Laplacian보다 강함을 검증(DESIGN §7 주장). 180도 twist에서 갈림.
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dyna_io.model import MeshData, SolidElement, ElementType  # noqa: E402
from morph.laplacian import morph_laplacian  # noqa: E402
from morph.rbf import morph_rbf  # noqa: E402
from morph.quality import check_quality  # noqa: E402


def _column(nx=3, ny=3, nz=8, L=10.0):
    """세로로 긴 hex 기둥."""
    m = MeshData()
    g = {}
    nid = 1
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                m.nodes[nid] = (L * i / nx, L * j / ny, L * k / nz * 3)
                g[(i, j, k)] = nid
                nid += 1
    e = 1
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                n = [g[(i, j, k)], g[(i + 1, j, k)], g[(i + 1, j + 1, k)], g[(i, j + 1, k)],
                     g[(i, j, k + 1)], g[(i + 1, j, k + 1)], g[(i + 1, j + 1, k + 1)], g[(i, j + 1, k + 1)]]
                m.solids.append(SolidElement(e, 1, n, ElementType.HEX8))
                e += 1
    return m


class _RS:
    def __init__(self, e, n2r):
        self.eid = e.eid
        self.pid = e.pid
        self.node_ids = [n2r[n] for n in e.node_ids]
        self.etype = e.etype


def _twist_disp(X, bnd, ctr, deg):
    th = np.radians(deg)
    R = np.array([[np.cos(th), -np.sin(th), 0], [np.sin(th), np.cos(th), 0], [0, 0, 1]])
    return np.array([R @ (X[b] - ctr) - (X[b] - ctr) for b in bnd])


def _setup():
    m = _column()
    X, n2r, r2n = m.dense_index(solids_only=True)
    rs = [_RS(e, n2r) for e in m.solids]
    zmax = X[:, 2].max()
    bnd = np.where(np.abs(X[:, 2] - zmax) < 1e-6)[0]
    ctr = np.array([5.0, 5.0, zmax])
    return X, rs, bnd, ctr


def test_rbf_survives_180deg_twist_where_laplacian_inverts():
    """180도 twist: Laplacian은 요소 뒤집힘, RBF는 유효(DESIGN §7 핵심 주장)."""
    X, rs, bnd, ctr = _setup()
    disp = _twist_disp(X, bnd, ctr, 180)

    q_lap = check_quality(morph_laplacian(X, rs, bnd, disp), rs, X)
    q_rbf = check_quality(morph_rbf(X, bnd, disp), rs, X)

    assert q_lap["inverted"], "180도에서 Laplacian은 뒤집혀야 함(주장의 전제)"
    assert not q_rbf["inverted"], "RBF는 회전에 강해 뒤집히지 않아야 함"
    assert q_rbf["min_jacobian"] > 0


def test_rbf_small_rotation_valid():
    """작은 회전(90도)은 둘 다 유효하되 RBF 품질이 더 높음."""
    X, rs, bnd, ctr = _setup()
    disp = _twist_disp(X, bnd, ctr, 90)
    q_lap = check_quality(morph_laplacian(X, rs, bnd, disp), rs, X)
    q_rbf = check_quality(morph_rbf(X, bnd, disp), rs, X)
    assert not q_lap["inverted"] and not q_rbf["inverted"]
    assert q_rbf["min_jacobian"] >= q_lap["min_jacobian"]
