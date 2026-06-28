# 슬라이스5: app 파이프라인 end-to-end + MCP 서버 도구 등록/스키마 검증.
import asyncio
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tests" / "fixtures"))

from app.session import GripState, PhoneStage, HandStage  # noqa: E402
from app import pipeline  # noqa: E402
from app.blender_io import _blender_bin  # noqa: E402
from make_phone_k import make_phone_k  # noqa: E402

_HAS_BLENDER = os.path.exists(_blender_bin())
blender_required = pytest.mark.skipif(not _HAS_BLENDER, reason="Blender 없음")


def test_session_roundtrip(tmp_path):
    """GripState 디스크 영속 왕복."""
    st = GripState(session_id="s1", workdir=str(tmp_path / "s1"))
    st.phone_stage = PhoneStage.EXTRACTED
    st.artifacts["phone_outer"] = "/x/y.stl"
    st.save()
    st2 = GripState.load(st.workdir)
    assert st2.phone_stage == PhoneStage.EXTRACTED
    assert st2.artifacts["phone_outer"] == "/x/y.stl"


def test_extract_then_morph_no_blender(tmp_path):
    """Blender 없이도 도는 경로: extract → (직접 편집외곽) → morph → export."""
    k = tmp_path / "phone.k"
    make_phone_k(str(k))
    st = GripState.load_or_create("s2", str(tmp_path / "sess"))

    r = pipeline.extract_surface(st, str(k))
    assert r.ok and st.phone_stage == PhoneStage.EXTRACTED

    # 그립 없이 외곽을 직접 살짝 변형해 모핑 입력 생성
    import struct
    src = st.artifacts["phone_outer"]
    edited = str(tmp_path / "edited.stl")
    with open(src, "rb") as f:
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
    assert r.ok, r.message
    assert st.phone_stage == PhoneStage.MORPHED

    out = str(tmp_path / "out.k")
    r = pipeline.export_solid_k(st, out)
    assert r.ok and os.path.exists(out)


def test_inspect_k(tmp_path):
    """inspect_k가 PART 구조를 반환."""
    k = tmp_path / "phone.k"
    make_phone_k(str(k))
    r = pipeline.inspect_k(str(k))
    assert r.ok
    assert 1 in r.diagnostics["parts"]   # PID 1


def test_stage_gates(tmp_path):
    """순서 게이트: 폰 없이 load_hand, 손 없이 grip은 실패."""
    st = GripState.load_or_create("s3", str(tmp_path / "sess"))
    assert not pipeline.load_hand(st).ok          # 폰 미추출
    assert not pipeline.grip_phone(st).ok          # 손 미로드


def test_mcp_tools_flat_schema():
    """MCP 도구가 flat 인자로 등록되는지(args 중첩 금지)."""
    from mcp_server.server import mcp

    async def _check():
        tools = await mcp.list_tools()
        names = {t.name for t in tools}
        assert {"extract_surface", "inspect_k", "load_hand",
                "grip_phone", "morph_phone", "export_solid_k"} <= names
        for t in tools:
            props = list(t.inputSchema.get("properties", {}).keys())
            assert "args" not in props        # flat
        return len(tools)

    assert asyncio.run(_check()) >= 6


@blender_required
def test_full_pipeline_with_grip(tmp_path):
    """Blender 포함 전체: extract→load→grip→morph→export."""
    k = tmp_path / "phone.k"
    make_phone_k(str(k))
    st = GripState.load_or_create("full", str(tmp_path / "sess"))
    assert pipeline.extract_surface(st, str(k)).ok
    assert pipeline.load_hand(st, "right").ok
    assert pipeline.grip_phone(st, "natural").ok
    assert st.hand_stage == HandStage.GRIPPED
    r = pipeline.morph_phone(st, scale=1.0)
    assert r.ok, r.message
    assert pipeline.export_solid_k(st, str(tmp_path / "final.k")).ok
