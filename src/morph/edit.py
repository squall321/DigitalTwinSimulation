# 폰 외곽 STL을 파라메트릭 편집해 모핑 입력(edited_outer)을 생성. GUI 없이 폼팩터 변경.
import struct

import numpy as np


def _read_stl(path):
    """binary STL → (삼각형 (n,3,3), 법선 (n,3))."""
    with open(path, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        tris = np.zeros((n, 3, 3), dtype=np.float64)
        norms = np.zeros((n, 3), dtype=np.float64)
        for i in range(n):
            norms[i] = struct.unpack("<3f", f.read(12))
            for j in range(3):
                tris[i, j] = struct.unpack("<3f", f.read(12))
            f.read(2)
    return tris, norms


def _write_stl(path, tris):
    """삼각형 (n,3,3) → binary STL. 법선 재계산."""
    tris = np.asarray(tris, dtype=np.float64)
    with open(path, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(tris)))
        for t in tris:
            nrm = np.cross(t[1] - t[0], t[2] - t[0])
            ln = np.linalg.norm(nrm)
            nrm = nrm / ln if ln > 1e-12 else np.zeros(3)
            f.write(struct.pack("<3f", *nrm))
            for v in t:
                f.write(struct.pack("<3f", *v))
            f.write(b"\0\0")


def scale_thickness(in_stl, out_stl, factor, axis=2):
    """지정 축(기본 z=두께)을 factor배 스케일. 폰을 얇거나 두껍게.

    바운딩박스 중심을 기준으로 스케일해 위치를 유지한다.
    """
    tris, _ = _read_stl(in_stl)
    V = tris.reshape(-1, 3)
    c = (V[:, axis].min() + V[:, axis].max()) * 0.5
    tris[:, :, axis] = c + (tris[:, :, axis] - c) * factor
    _write_stl(out_stl, tris)
    return {"op": "scale_thickness", "factor": factor, "axis": axis}


def round_corners(in_stl, out_stl, radius, axis=2):
    """축에 수직한 평면(폰 앞/뒤면)에서 바깥 모서리를 radius만큼 안으로 당겨 둥글게.

    각 정점의 평면상 위치가 바운딩박스 코너에 가까울수록 안쪽으로 이동시킨다.
    간이 코너 라운딩 — 정밀 CAD 필렛이 아니라 폼팩터 근사.
    """
    tris, _ = _read_stl(in_stl)
    V = tris.reshape(-1, 3)
    ax = [i for i in range(3) if i != axis]           # 평면 두 축
    lo = V[:, ax].min(axis=0)
    hi = V[:, ax].max(axis=0)
    half = (hi - lo) * 0.5
    ctr = (hi + lo) * 0.5
    for t in tris:
        for v in t:
            p = v[ax] - ctr                            # 중심 기준 평면 좌표
            # 각 축에서 코너 근접도(0~1): |p|가 half-radius를 넘으면 라운딩 시작
            for d in range(2):
                over = abs(p[d]) - (half[d] - radius)
                if over > 0 and half[d] > radius:
                    # 코너 영역 → radius 원호 근사로 안쪽 당김
                    frac = min(over / radius, 1.0)
                    v[ax[d]] -= np.sign(p[d]) * radius * (1 - np.cos(frac * np.pi / 2))
    _write_stl(out_stl, tris)
    return {"op": "round_corners", "radius": radius, "axis": axis}


def dent(in_stl, out_stl, center, radius, depth, axis=2):
    """국소 함몰. center(평면 좌표) 반경 radius 안의 면을 axis방향으로 depth 눌러 넣음.

    center: 평면 두 좌표 (axis 제외). radius/depth: mm.
    가우시안 프로파일로 부드러운 함몰(드롭 충격 자국 등).
    """
    tris, _ = _read_stl(in_stl)
    ax = [i for i in range(3) if i != axis]
    c = np.asarray(center, dtype=np.float64)
    for t in tris:
        for v in t:
            r = np.linalg.norm(v[ax] - c)
            if r < radius * 2.5:
                v[axis] -= depth * np.exp(-(r ** 2) / (2 * (radius / 2) ** 2))
    _write_stl(out_stl, tris)
    return {"op": "dent", "center": list(center), "radius": radius, "depth": depth}
