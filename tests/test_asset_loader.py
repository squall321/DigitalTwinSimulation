# 10번: 손 에셋(OBJ) 임포트 로더 검증. HandLoader 두 번째 구현 → Strategy 정당화.
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from hand.loader import AssetHandLoader, HandLoader, bake_procedural_asset  # noqa: E402
from hand.procedural import ProceduralHandBuilder  # noqa: E402
from hand.types import RiggedHand  # noqa: E402
from app.blender_io import run_headless, _blender_bin  # noqa: E402

_HAS_BLENDER = os.path.exists(_blender_bin())
blender_required = pytest.mark.skipif(not _HAS_BLENDER, reason="Blender 없음")


def test_both_loaders_satisfy_protocol():
    """절차/에셋 로더가 동일 HandLoader 계약(build 메서드)을 만족 → Strategy 성립."""
    proc = ProceduralHandBuilder()
    asset = AssetHandLoader("/nonexistent.obj")
    assert hasattr(proc, "build") and hasattr(asset, "build")
    # 구조적 서브타이핑 확인(런타임)
    assert callable(getattr(proc, "build"))
    assert callable(getattr(asset, "build"))


def test_asset_loader_missing_file():
    """없는 에셋은 명확한 에러."""
    loader = AssetHandLoader("/does/not/exist.obj")
    with pytest.raises(FileNotFoundError):
        loader.build(run_headless)


@blender_required
def test_bake_and_import_roundtrip(tmp_path):
    """절차 손 → OBJ 베이크 → AssetHandLoader 임포트 → RiggedHand."""
    obj = str(tmp_path / "hand.obj")
    baked = bake_procedural_asset(run_headless, obj, workdir=str(tmp_path / "bake"))
    assert os.path.exists(obj) and baked["obj_bytes"] > 1000

    loader = AssetHandLoader(obj, handedness="right")
    stl = str(tmp_path / "reimport.stl")
    hand = loader.build(run_headless, workdir=str(tmp_path / "imp"), export_stl=stl)
    assert isinstance(hand, RiggedHand)
    assert hand.object_name == "Hand"
    assert os.path.exists(stl)
