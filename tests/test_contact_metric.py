# 슬라이스3 확장: 접촉 면적/밀착도 측정 검증. Blender 통합(grip 실행) 필요.
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))

from app.blender_io import run_headless, _blender_bin  # noqa: E402
from make_phone_k import make_phone_k  # noqa: E402

_HAS_BLENDER = os.path.exists(_blender_bin())
blender_required = pytest.mark.skipif(not _HAS_BLENDER, reason="Blender 없음")


@blender_required
def test_contact_metrics_present(tmp_path):
    """그립 후 penetration dict에 접촉 지표(contact_verts/ratio/min_gap)가 포함된다."""
    make_phone_k(str(tmp_path / "phone.k"))
    # 외곽 STL 생성
    from dyna_io.parser import parse_k_file
    from dyna_io.surface import build_surface
    from dyna_io.stl import write_stl
    m = parse_k_file(str(tmp_path / "phone.k"))
    tris, used, _ = build_surface(m)
    verts = [tuple(m.nodes[nid]) for nid in used]
    outer = str(tmp_path / "outer.stl")
    write_stl(outer, verts, tris, binary=True)

    r = run_headless({"op": "grip_phone", "params": {
        "phone_stl": outer, "style": "natural", "handedness": "right",
        "hand_stl": str(tmp_path / "hand.stl")}}, workdir=str(tmp_path / "wd"))
    assert r["ok"], r.get("error")
    p = r["result"]["penetration"]

    # 접촉 지표 존재 + 타입
    assert "contact_verts" in p
    assert "contact_ratio" in p
    assert "min_gap" in p
    assert 0.0 <= p["contact_ratio"] <= 1.0
    assert p["min_gap"] is None or p["min_gap"] >= 0
    # 손이 폰 근처에 있으므로 최소갭은 유한하고 작아야(합성 폰 기준 <10mm)
    assert p["min_gap"] is not None and p["min_gap"] < 10.0
    # 관통 깊이는 기하학적 상한(폰 반두께 4mm) 이내 — 패리티 판정의 타당성
    # (이전 법선 dot 부호 판정은 58mm 같은 불가능값을 냈음)
    assert p["max_penetration"] <= 4.0 + 1e-6
