# 변위장 u의 조화확장(harmonic extension). 좌표가 아니라 변위를 푼다(L u = 0, 내부).
from dataclasses import dataclass

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve


@dataclass
class _RowElem:
    """laplacian 엣지 구성용: node_ids가 NID가 아니라 dense 행 인덱스인 가벼운 요소."""
    node_ids: list


def row_elems(elems, nid2row):
    """솔리드 요소의 node_ids(NID)를 dense 행 인덱스로 변환한 _RowElem 리스트.

    dense_index에 포함되지 않은 노드(고립)는 건너뛴다.
    """
    out = []
    for el in elems:
        rows = [nid2row[n] for n in el.node_ids if n in nid2row]
        out.append(_RowElem(rows))
    return out


def _edges_from_elems(elems, nid2row):
    """솔리드 요소들의 고유 노드 쌍에서 그래프 엣지 집합 생성.

    collapse된 degenerate 슬롯의 자기엣지를 배제하려 dict.fromkeys로 고유화.
    elems의 node_ids는 dense row index로 변환된다(nid2row).
    returns set of (i, j) with i < j (row index).
    """
    edges = set()
    for el in elems:
        u = list(dict.fromkeys(el.node_ids))
        rows = [nid2row[n] for n in u if n in nid2row]
        m = len(rows)
        for a in range(m):
            for b in range(a + 1, m):
                i, j = rows[a], rows[b]
                if i == j:
                    continue
                edges.add((i, j) if i < j else (j, i))
    return edges


def build_laplacian(X, edges, inverse_dist=True):
    """그래프 라플라시안 L (N,N) CSR.

    Args:
      X: (N,3) 노드 좌표.
      edges: (i, j) 행인덱스 쌍 iterable (i < j).
      inverse_dist: True면 가중치 1/|xi-xj|, False면 1(균일).
    epsilon 가드로 degenerate 0거리에서 발산 방지(검증 D4).
    """
    X = np.asarray(X, dtype=np.float64).reshape(-1, 3)
    n = X.shape[0]
    rows = []
    cols = []
    vals = []
    eps = 1e-9
    for i, j in edges:
        if inverse_dist:
            d = np.linalg.norm(X[i] - X[j])
            w = 1.0 / max(d, eps)
        else:
            w = 1.0
        rows += [i, j]
        cols += [j, i]
        vals += [-w, -w]
    W = sp.csr_matrix((vals, (rows, cols)), shape=(n, n))
    deg = -np.asarray(W.sum(axis=1)).ravel()      # 행 합의 음수 = degree
    L = W + sp.diags(deg)
    return L.tocsr()


def morph_laplacian(X, elems, bnd_idx, bnd_disp):
    """변위장 u의 조화확장으로 내부 노드를 재배치. X' = X + u 반환.

    L_II u_I = -L_IB u_B 를 spsolve 다중 rhs(3축)로 푼다.
    내부 노드가 0개면(단일요소/셸-only) no-op로 X를 그대로 반환(검증 D2).

    Args:
      X: (N,3) 현재 좌표.
      elems: 솔리드 요소 리스트(node_ids는 NID). nid2row를 위해 row2nid가 필요하므로
             여기서는 elems의 node_ids가 '행 인덱스'가 아니라 NID라고 가정하고,
             호출자가 dense_index를 1회 만들어 일관된 X/bnd_idx를 넘긴다.
             엣지 구성은 nid2row 매핑이 필요 → driver가 row 기반 elems를 넘기도록
             _RowElem 래핑을 사용(아래 build helper 참조).
      bnd_idx: 경계 노드의 행 인덱스 배열.
      bnd_disp: (len(bnd_idx), 3) 경계 변위.
    """
    X = np.asarray(X, dtype=np.float64).reshape(-1, 3)
    n = X.shape[0]
    bnd_idx = np.asarray(bnd_idx, dtype=np.intp).ravel()
    bnd_disp = np.asarray(bnd_disp, dtype=np.float64).reshape(-1, 3)

    bnd_set = set(int(i) for i in bnd_idx)
    int_idx = np.array([i for i in range(n) if i not in bnd_set], dtype=np.intp)

    u = np.zeros((n, 3), dtype=np.float64)
    u[bnd_idx] = bnd_disp

    if int_idx.size == 0:
        return X + u  # 내부 노드 없음 → 경계 변위만 적용

    # elems는 driver가 row-index node_ids로 넘긴다(identity nid2row).
    nid2row = {i: i for i in range(n)}
    edges = _edges_from_elems(elems, nid2row)
    L = build_laplacian(X, edges)

    L_II = L[int_idx][:, int_idx]
    L_IB = L[int_idx][:, bnd_idx]
    rhs = -L_IB @ bnd_disp                         # (n_int, 3)

    u_int = spsolve(L_II.tocsc(), rhs)
    u_int = np.asarray(u_int).reshape(int_idx.size, 3)
    u[int_idx] = u_int
    return X + u
