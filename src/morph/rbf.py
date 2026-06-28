# Thin-Plate-Spline RBF 모핑. 경계노드 B 기준 O(B^3) — 회전/비연결 입력 전용 대안.
import numpy as np


def _tps_kernel(r):
    """TPS 기저 phi(r) = r^2 log(r). r=0에서 0."""
    out = np.zeros_like(r)
    nz = r > 1e-12
    out[nz] = r[nz] ** 2 * np.log(r[nz])
    return out


def morph_rbf(X, bnd_idx, bnd_disp):
    """경계 변위를 TPS RBF로 전 노드에 보간해 X' = X + u 반환.

    제어점 = 경계 노드 B개. 시스템 크기는 (B+4) → O(B^3). 압입엔 약하고
    회전/비연결 변형에 강하다(DESIGN §7). B가 수천을 넘으면 비용 경고는
    driver가 사전 체크.

    Args:
      X: (N,3) 좌표.
      bnd_idx: 경계 노드 행 인덱스.
      bnd_disp: (len(bnd_idx),3) 경계 변위.
    """
    X = np.asarray(X, dtype=np.float64).reshape(-1, 3)
    bnd_idx = np.asarray(bnd_idx, dtype=np.intp).ravel()
    bnd_disp = np.asarray(bnd_disp, dtype=np.float64).reshape(-1, 3)

    P = X[bnd_idx]                                  # (B,3) 제어점
    B = P.shape[0]
    if B == 0:
        return X.copy()

    # 제어점 간 거리 행렬 → TPS 커널
    diff = P[:, None, :] - P[None, :, :]
    r = np.linalg.norm(diff, axis=2)
    K = _tps_kernel(r)                              # (B,B)

    # affine 항 [1, x, y, z]
    Pa = np.hstack([np.ones((B, 1)), P])            # (B,4)

    # 블록 시스템 [[K, Pa],[Pa^T, 0]] w = [disp; 0]
    A = np.zeros((B + 4, B + 4), dtype=np.float64)
    A[:B, :B] = K
    A[:B, B:] = Pa
    A[B:, :B] = Pa.T
    rhs = np.zeros((B + 4, 3), dtype=np.float64)
    rhs[:B] = bnd_disp

    sol = np.linalg.solve(A, rhs)                   # (B+4, 3)
    w = sol[:B]                                     # (B,3) RBF 가중
    a = sol[B:]                                     # (4,3) affine

    # 전 노드 평가
    diff2 = X[:, None, :] - P[None, :, :]
    r2 = np.linalg.norm(diff2, axis=2)              # (N,B)
    Phi = _tps_kernel(r2)
    Xa = np.hstack([np.ones((X.shape[0], 1)), X])   # (N,4)
    u = Phi @ w + Xa @ a                            # (N,3)
    return X + u
