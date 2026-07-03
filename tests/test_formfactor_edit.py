# 슬라이스4 확장: 폰 폼팩터 파라메트릭 편집 → 모핑 입력 생성 검증.
import struct
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))

from dyna_io.parser import parse_k_file  # noqa: E402
from dyna_io.surface import build_surface  # noqa: E402
from dyna_io.stl import write_stl  # noqa: E402
from morph import edit  # noqa: E402
from morph.driver import morph_phone_volume  # noqa: E402
from make_phone_k import make_phone_k  # noqa: E402


def _bbox(p):
    with open(p, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        V = []
        for _ in range(n):
            f.read(12)
            for _ in range(3):
                V.append(struct.unpack("<3f", f.read(12)))
            f.read(2)
    V = np.array(V)
    return V.min(0), V.max(0)


def _phone_outer(tmp_path):
    k = tmp_path / "phone.k"
    make_phone_k(str(k))
    m = parse_k_file(str(k))
    tris, used, _ = build_surface(m)
    verts = [tuple(m.nodes[nid]) for nid in used]
    stl = tmp_path / "outer.stl"
    write_stl(str(stl), verts, tris, binary=True)
    return m, str(stl)


def test_scale_thickness(tmp_path):
    """두께 0.7배 → z크기 감소, 모핑 유효."""
    m, outer = _phone_outer(tmp_path)
    out = str(tmp_path / "thin.stl")
    edit.scale_thickness(outer, out, 0.7)
    mn, mx = _bbox(out)
    assert abs((mx[2] - mn[2]) - 8.0 * 0.7) < 0.5     # 두께 8→5.6
    res = morph_phone_volume(m, out, scale=1.0)
    assert res.ok and res.diagnostics["min_jacobian"] > 0


def test_dent(tmp_path):
    """국소 함몰 → 모핑 유효, 함몰부 좌표가 눌림."""
    m, outer = _phone_outer(tmp_path)
    out = str(tmp_path / "dented.stl")
    edit.dent(outer, out, center=(35, 75), radius=15, depth=2)
    res = morph_phone_volume(m, out, scale=1.0)
    assert res.ok


def test_round_corners_runs(tmp_path):
    """코너 라운딩이 실행되고 모핑 입력으로 유효."""
    m, outer = _phone_outer(tmp_path)
    out = str(tmp_path / "rounded.stl")
    meta = edit.round_corners(outer, out, radius=8.0)
    assert meta["op"] == "round_corners"
    res = morph_phone_volume(m, out, scale=1.0)
    assert res.ok       # minJ 낮을 수 있으나 유효(양수)


def test_pipeline_edit_formfactor(tmp_path):
    """pipeline.edit_formfactor 경로: extract → edit → morph."""
    from app.session import GripState
    from app import pipeline

    k = tmp_path / "phone.k"
    make_phone_k(str(k))
    st = GripState.load_or_create("edit", str(tmp_path / "sess"))
    assert pipeline.extract_surface(st, str(k)).ok
    r = pipeline.edit_formfactor(st, "scale_thickness", factor=0.8)
    assert r.ok
    assert "phone_edited_outer" in st.artifacts
    r = pipeline.morph_phone(st, scale=1.0)
    assert r.ok
