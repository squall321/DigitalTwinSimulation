# aspect 게이트 회귀: 뒤집힘 없는 순수 인장이 near-sliver로 거부되는지(원본 대비 성장률 기준).
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))

from dyna_io.parser import parse_k_file  # noqa: E402
from dyna_io.surface import build_surface  # noqa: E402
from dyna_io.stl import write_stl  # noqa: E402
from morph.driver import morph_phone_volume  # noqa: E402
from morph import edit  # noqa: E402
from make_phone_k import make_phone_k  # noqa: E402


def _phone_outer(tmp_path):
    k = tmp_path / "phone.k"
    make_phone_k(str(k))
    mesh = parse_k_file(str(k))
    tris, used, _ = build_surface(mesh)
    verts = [tuple(mesh.nodes[nid]) for nid in used]
    stl = tmp_path / "outer.stl"
    write_stl(str(stl), verts, tris, binary=True)
    return mesh, str(stl)


def test_pure_stretch_rejected_by_aspect_gate(tmp_path):
    """두께 8배 인장: 뒤집힘 없이 aspect만 악화 → aspect 게이트가 거부해야 한다."""
    mesh, outer = _phone_outer(tmp_path)
    stretched = str(tmp_path / "stretched.stl")
    edit.scale_thickness(outer, stretched, 8.0)     # z 8→64mm, aspect ~2.4배 성장

    res = morph_phone_volume(mesh, stretched, scale=1.0)
    assert not res.ok
    assert "aspect" in res.message                   # 뒤집힘이 아니라 aspect 사유
    assert "suggested_scale" in res.diagnostics


def test_normal_dent_passes_aspect_gate(tmp_path):
    """정상 함몰(0.5mm): aspect 성장 미미 → 통과, baseline_aspect 진단 포함."""
    mesh, outer = _phone_outer(tmp_path)
    dented = str(tmp_path / "dented.stl")
    edit.dent(outer, dented, center=(35, 75), radius=15, depth=0.5)

    res = morph_phone_volume(mesh, dented, scale=1.0)
    assert res.ok, res.message
    assert res.diagnostics["baseline_aspect"] > 0
    assert res.diagnostics["aspect_max"] <= res.diagnostics["baseline_aspect"] * 5.0


def test_aspect_growth_param_strict(tmp_path):
    """max_aspect_growth를 조이면(1.01) 정상 함몰도 aspect 사유로 거부 — 파라미터가 게이트를 제어."""
    mesh, outer = _phone_outer(tmp_path)
    dented = str(tmp_path / "dented.stl")
    edit.dent(outer, dented, center=(35, 75), radius=15, depth=0.5)

    res = morph_phone_volume(mesh, dented, scale=1.0, max_aspect_growth=1.01)
    assert not res.ok
    assert "aspect" in res.message
