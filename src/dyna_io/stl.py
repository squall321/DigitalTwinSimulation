# STL 라이터(binary/ascii)와 watertight 진단. 법선은 삼각형 winding에서 계산(외향 정렬 전제).
import struct

import numpy as np


def _tri_normals(verts, tris):
    """각 삼각형의 단위 법선(우수 winding). verts(N,3), tris(M,3) -> (M,3)."""
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(tris, dtype=np.intp).reshape(-1, 3)
    p0 = v[t[:, 0]]
    p1 = v[t[:, 1]]
    p2 = v[t[:, 2]]
    n = np.cross(p1 - p0, p2 - p0)
    norm = np.linalg.norm(n, axis=1)
    norm[norm < 1e-30] = 1.0
    return n / norm[:, None]


def write_stl(path, verts, tris, binary=True):
    """삼각형 표면을 STL로 기록.

    Args:
      path: 출력 경로.
      verts: (N,3) 정점 좌표.
      tris: (M,3) 정점 인덱스 삼각형(외향 winding 전제).
      binary: True면 binary STL, False면 ASCII.
    """
    v = np.asarray(verts, dtype=np.float64).reshape(-1, 3)
    t = np.asarray(tris, dtype=np.intp).reshape(-1, 3)
    normals = _tri_normals(v, t)

    if binary:
        _write_binary(path, v, t, normals)
    else:
        _write_ascii(path, v, t, normals)


def _write_binary(path, v, t, normals):
    with open(path, "wb") as f:
        f.write(b"\x00" * 80)                       # 80바이트 헤더
        f.write(struct.pack("<I", len(t)))          # 삼각형 수
        for i in range(len(t)):
            nx, ny, nz = normals[i]
            a, b, c = v[t[i, 0]], v[t[i, 1]], v[t[i, 2]]
            f.write(struct.pack("<12f",
                                nx, ny, nz,
                                a[0], a[1], a[2],
                                b[0], b[1], b[2],
                                c[0], c[1], c[2]))
            f.write(struct.pack("<H", 0))           # attribute byte count


def _write_ascii(path, v, t, normals):
    lines = ["solid dts"]
    for i in range(len(t)):
        nx, ny, nz = normals[i]
        a, b, c = v[t[i, 0]], v[t[i, 1]], v[t[i, 2]]
        lines.append(f"facet normal {nx:.6e} {ny:.6e} {nz:.6e}")
        lines.append("  outer loop")
        for p in (a, b, c):
            lines.append(f"    vertex {p[0]:.6e} {p[1]:.6e} {p[2]:.6e}")
        lines.append("  endloop")
        lines.append("endfacet")
    lines.append("endsolid dts")
    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")


def read_stl_points(path):
    """STL(binary/ascii)에서 고유 정점 좌표 (P,3)만 읽는다.

    삼각형 연결성은 버리고 점 구름만 반환(모핑 경계 되투영용 cKDTree 입력).
    binary/ascii 자동 판별: 헤더가 'solid'로 시작하고 'facet'을 포함하면 ascii.
    """
    with open(path, "rb") as f:
        head = f.read(512)
    is_ascii = head[:5].lower() == b"solid" and b"facet" in head.lower()

    pts = []
    if is_ascii:
        with open(path, "r", errors="ignore") as f:
            for line in f:
                s = line.strip()
                if s.startswith("vertex"):
                    _, x, y, z = s.split()[:4]
                    pts.append((float(x), float(y), float(z)))
    else:
        with open(path, "rb") as f:
            f.read(80)
            (n_tri,) = struct.unpack("<I", f.read(4))
            for _ in range(n_tri):
                data = f.read(50)
                vals = struct.unpack("<12f", data[:48])
                pts.append((vals[3], vals[4], vals[5]))
                pts.append((vals[6], vals[7], vals[8]))
                pts.append((vals[9], vals[10], vals[11]))

    arr = np.asarray(pts, dtype=np.float64).reshape(-1, 3)
    if len(arr) == 0:
        return arr
    return np.unique(arr, axis=0)


def watertight_diag(tris):
    """삼각형 표면의 닫힘성 진단.

    Returns:
      {"n_tris", "n_edges", "non_manifold_edges", "boundary_edges",
       "watertight"}.
        non_manifold_edges: 3개 이상 삼각형이 공유하는 에지 수.
        boundary_edges: 1개 삼각형만 가진(열린) 에지 수.
        watertight: 모든 에지가 정확히 2개 삼각형에 공유.
    """
    from collections import Counter

    ec = Counter()
    for tri in tris:
        a, b, c = tri
        for e in ((a, b), (b, c), (c, a)):
            ec[frozenset(e)] += 1
    boundary = sum(1 for cnt in ec.values() if cnt == 1)
    nonmanifold = sum(1 for cnt in ec.values() if cnt >= 3)
    return {
        "n_tris": len(tris),
        "n_edges": len(ec),
        "non_manifold_edges": nonmanifold,
        "boundary_edges": boundary,
        "watertight": bool(tris) and boundary == 0 and nonmanifold == 0,
    }
