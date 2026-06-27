# 슬라이스2: 절차적 손 빌더를 headless Blender 경계로 검증하는 통합 테스트.
import os
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.blender_io import run_headless, _blender_bin  # noqa: E402
from hand.procedural import ProceduralHandBuilder  # noqa: E402
from hand.types import RiggedHand  # noqa: E402

# Blender 바이너리 없으면 통합 테스트 스킵(포터블 — CI 환경 무관).
_HAS_BLENDER = shutil.which(_blender_bin()) is not None or os.path.exists(_blender_bin())
blender_required = pytest.mark.skipif(not _HAS_BLENDER, reason="Blender 바이너리 없음")


def test_rigged_hand_dict_roundtrip():
    """RiggedHand 직렬화 왕복 — bpy 불필요한 순수 단위 테스트."""
    h = RiggedHand(object_name="Hand", armature_name="HandRig",
                   finger_chains={"index": ["index_01", "index_02"]},
                   blendshapes={"fist": "fist"}, unit_scale=1000.0)
    assert RiggedHand.from_dict(h.to_dict()) == h


@blender_required
def test_build_hand_headless(tmp_path):
    """py3.10 → run_headless → Blender py3.11 손 빌드 → JSON 회수."""
    builder = ProceduralHandBuilder(handedness="right", unit_scale=1000.0)
    stl = tmp_path / "hand.stl"
    hand = builder.build(run_headless, workdir=str(tmp_path), export_stl=str(stl))

    assert isinstance(hand, RiggedHand)
    assert len(hand.finger_chains) == 5
    for fname in ("thumb", "index", "middle", "ring", "pinky"):
        assert len(hand.finger_chains[fname]) == 3   # 각 손가락 3관절
    assert hand.unit_scale == 1000.0
    assert stl.exists() and stl.stat().st_size > 1000


@blender_required
def test_build_hand_left(tmp_path):
    """왼손도 생성되는지."""
    builder = ProceduralHandBuilder(handedness="left", unit_scale=1.0)
    hand = builder.build(run_headless, workdir=str(tmp_path))
    assert hand.handedness == "left"
    assert len(hand.finger_chains) == 5
