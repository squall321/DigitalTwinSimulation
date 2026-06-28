# Laplacian 조화확장 모핑 검증: 경계 한 면을 밀 때 내부노드가 0~d 사이 단조 추종, 단일요소 no-op.
from dataclasses import dataclass

import numpy as np

from morph.laplacian import morph_laplacian


@dataclass
class _RowElem:
    """node_ids가 dense 행 인덱스인 가벼운 요소(테스트용)."""
    node_ids: list


def _hex_grid(nx, ny, nz, spacing=1.0):
    """nx*ny*nz hex 격자의 (X, hex요소(행인덱스 node_ids), coord->row) 생성."""
    coord2row = {}
    coords = []

    def row(i, j, k):
        key = (i, j, k)
        if key not in coord2row:
            coord2row[key] = len(coords)
            coords.append((i * spacing, j * spacing, k * spacing))
        return coord2row[key]

    elems = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                n = [row(i, j, k), row(i + 1, j, k),
                     row(i + 1, j + 1, k), row(i, j + 1, k),
                     row(i, j, k + 1), row(i + 1, j, k + 1),
                     row(i + 1, j + 1, k + 1), row(i, j + 1, k + 1)]
                elems.append(_RowElem(n))
    X = np.array(coords, dtype=np.float64)
    return X, elems, coord2row


def test_push_one_face_interior_follows_smoothly():
    # 2x2x2 hex 격자: x=0 면을 -x 방향이 아닌, x=max 면을 +d 만큼 민다.
    nx = ny = nz = 2
    X, elems, coord2row = _hex_grid(nx, ny, nz, spacing=1.0)
    n = X.shape[0]

    d = 0.5
    xmax = nx  # i 인덱스 최대
    # 모든 경계(외피) 노드 = i,j,k 중 하나가 0 또는 최대인 노드.
    bnd_rows = []
    bnd_disp = []
    for (i, j, k), r in coord2row.items():
        on_surface = i in (0, nx) or j in (0, ny) or k in (0, nz)
        if not on_surface:
            continue
        bnd_rows.append(r)
        # x=max 면만 +d 이동, 나머지 경계는 고정(0 변위).
        if i == xmax:
            bnd_disp.append((d, 0.0, 0.0))
        else:
            bnd_disp.append((0.0, 0.0, 0.0))

    bnd_rows = np.array(bnd_rows, dtype=np.intp)
    bnd_disp = np.array(bnd_disp, dtype=np.float64)

    # 내부 노드는 정확히 중앙(1,1,1) 하나.
    center_row = coord2row[(1, 1, 1)]
    assert center_row not in set(bnd_rows.tolist())

    Xp = morph_laplacian(X, elems, bnd_rows, bnd_disp)

    ux = Xp[center_row, 0] - X[center_row, 0]
    # 내부 노드의 x변위가 0과 d 사이(매끄러운 추종).
    assert 0.0 < ux < d
    # 횡방향(y,z) 변위는 대칭이라 ~0.
    assert abs(Xp[center_row, 1] - X[center_row, 1]) < 1e-6
    assert abs(Xp[center_row, 2] - X[center_row, 2]) < 1e-6
    # 경계 노드는 지정 변위 그대로.
    assert np.allclose(Xp[bnd_rows], X[bnd_rows] + bnd_disp)


def test_monotone_through_thickness():
    # 두께방향(x)으로 여러 내부층이 있을 때, x=max 면을 밀면 내부 변위가 단조 증가.
    nx, ny, nz = 4, 1, 1
    X, elems, coord2row = _hex_grid(nx, ny, nz, spacing=1.0)

    d = 0.4
    bnd_rows = []
    bnd_disp = []
    for (i, j, k), r in coord2row.items():
        on_surface = i in (0, nx) or j in (0, ny) or k in (0, nz)
        if not on_surface:
            continue
        # i==0 면은 고정, i==nx 면은 +d. 측면(j,k 경계)은 자유롭게 두면 내부가 되어버리므로
        # 측면도 경계로 두되 변위는 i 비례로 부드럽게(밀어붙임이 균일하도록).
        bnd_rows.append(r)
        bnd_disp.append((d * (i / nx), 0.0, 0.0))

    bnd_rows = np.array(bnd_rows, dtype=np.intp)
    bnd_disp = np.array(bnd_disp, dtype=np.float64)

    Xp = morph_laplacian(X, elems, bnd_rows, bnd_disp)

    # i=1,2,3 의 한 내부 라인(j=0,k=0 모서리는 경계지만 변위가 i비례라 단조 확인용으로 사용).
    rows_by_i = {}
    for (i, j, k), r in coord2row.items():
        rows_by_i.setdefault(i, []).append(r)
    mean_ux = []
    for i in range(nx + 1):
        rs = rows_by_i[i]
        mean_ux.append(float(np.mean(Xp[rs, 0] - X[rs, 0])))
    # x변위 평균이 i에 따라 단조 증가, 0~d 범위.
    assert mean_ux[0] == 0.0
    assert abs(mean_ux[-1] - d) < 1e-6
    for a, b in zip(mean_ux, mean_ux[1:]):
        assert b >= a - 1e-9
    assert all(0.0 <= v <= d + 1e-9 for v in mean_ux)


def test_single_element_no_internal_nodes_noop():
    # 단일 hex(내부노드 0개): 경계 변위만 적용되고 그 외 변형 없음.
    X, elems, coord2row = _hex_grid(1, 1, 1, spacing=1.0)
    n = X.shape[0]
    assert n == 8

    # 전체 8노드가 경계(내부노드 0개).
    bnd_rows = np.arange(n, dtype=np.intp)
    bnd_disp = np.zeros((n, 3), dtype=np.float64)
    bnd_disp[coord2row[(1, 1, 1)]] = (0.3, 0.0, 0.0)

    Xp = morph_laplacian(X, elems, bnd_rows, bnd_disp)
    # no-op 단락: X + u 그대로(경계 변위만).
    assert np.allclose(Xp, X + bnd_disp)
