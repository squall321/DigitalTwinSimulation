# 좌표의존 카드 경고가 rewrite→pipeline까지 전달되는지 검증(DESIGN §11 확정 항목).
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))

from dyna_io.parser import parse_k_file  # noqa: E402
from dyna_io.rewrite import rewrite_k  # noqa: E402
from make_phone_k import make_phone_k  # noqa: E402


def _phone_with_card(tmp_path, card):
    make_phone_k(str(tmp_path / "base.k"))
    txt = (tmp_path / "base.k").read_text().replace(
        "*END", f"{card}\n         1         0     -5000.0\n*END")
    p = tmp_path / "with_card.k"
    p.write_text(txt)
    return parse_k_file(str(p))


def test_initial_velocity_warns(tmp_path):
    """*INITIAL_VELOCITY_GENERATION이 있으면 rewrite가 경고한다."""
    m = _phone_with_card(tmp_path, "*INITIAL_VELOCITY_GENERATION")
    nc = {nid: m.nodes[nid] for nid in list(m.nodes)[:5]}
    r = rewrite_k(m, nc, str(tmp_path / "out.k"))
    assert "*INITIAL_VELOCITY_GENERATION" in r["coord_dependent_cards"]
    assert r["warnings"]


def test_no_warning_when_clean(tmp_path):
    """좌표의존 카드가 없으면 경고 없음."""
    make_phone_k(str(tmp_path / "clean.k"))
    m = parse_k_file(str(tmp_path / "clean.k"))
    nc = {nid: m.nodes[nid] for nid in list(m.nodes)[:5]}
    r = rewrite_k(m, nc, str(tmp_path / "out.k"))
    assert not r["warnings"]
    assert not r["coord_dependent_cards"]


def test_warning_propagates_to_pipeline(tmp_path):
    """morph_phone 결과 diagnostics에 경고가 실려 상위(MCP)까지 전달된다."""
    import struct
    from app.session import GripState
    from app import pipeline
    from dyna_io.surface import build_surface
    from dyna_io.stl import write_stl

    m = _phone_with_card(tmp_path, "*BOUNDARY_PRESCRIBED_MOTION")
    src_k = m.src_path
    st = GripState.load_or_create("warn", str(tmp_path / "sess"))
    st.src_k = src_k
    r = pipeline.extract_surface(st, src_k)
    assert r.ok

    # 외곽 살짝 변형해 모핑 입력 생성
    outer = st.artifacts["phone_outer"]
    edited = str(tmp_path / "edited.stl")
    with open(outer, "rb") as f:
        f.read(80)
        n = struct.unpack("<I", f.read(4))[0]
        data = []
        for _ in range(n):
            nrm = struct.unpack("<3f", f.read(12))
            vs = [list(struct.unpack("<3f", f.read(12))) for _ in range(3)]
            f.read(2)
            data.append((nrm, vs))
    for nrm, vs in data:
        for v in vs:
            if v[2] > 7.5:
                v[2] -= 0.3
    with open(edited, "wb") as f:
        f.write(b"\0" * 80)
        f.write(struct.pack("<I", len(data)))
        for nrm, vs in data:
            f.write(struct.pack("<3f", *nrm))
            for v in vs:
                f.write(struct.pack("<3f", *v))
            f.write(b"\0\0")

    r = pipeline.morph_phone(st, edited_outer=edited, scale=1.0)
    assert r.ok
    assert r.diagnostics.get("warnings")     # 경고가 morph 결과에 전달됨
