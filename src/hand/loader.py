# 손 로더 인터페이스(Protocol)와 에셋 임포트 로더. 두 번째 구현이 생겨 Strategy 패턴 정당화.
from pathlib import Path
from typing import Protocol

from hand.types import RiggedHand


class HandLoader(Protocol):
    """손을 로드해 RiggedHand 계약을 반환하는 로더. 절차적/에셋 구현이 공유."""

    def build(self, run_headless, workdir: str = None,
              export_stl: str = None) -> RiggedHand:
        ...


class AssetHandLoader:
    """OBJ 손 에셋을 임포트하는 로더. 사용자가 CC0 등 사실적 손 OBJ를 넣으면 사용.

    에셋이 리깅(본)을 포함하지 않으면, 절차적 빌더의 스켈레톤을 재사용하고
    메쉬만 교체하는 하이브리드가 필요하다(그립은 본을 회전시키므로). 현 구현은
    에셋 로드 + STL 재익스포트 경로를 검증한다. 본 매핑은 에셋에 armature가 있을 때 확장.
    """

    def __init__(self, asset_path: str, handedness: str = "right"):
        self.asset_path = asset_path
        self.handedness = handedness

    def build(self, run_headless, workdir: str = None,
              export_stl: str = None) -> RiggedHand:
        if not Path(self.asset_path).exists():
            raise FileNotFoundError(f"손 에셋 없음: {self.asset_path}")
        cmd = {"op": "import_hand_obj", "params": {
            "asset_path": self.asset_path,
            "handedness": self.handedness,
            "export_stl": export_stl,
        }}
        res = run_headless(cmd, workdir=workdir)
        if not res.get("ok"):
            raise RuntimeError(f"손 에셋 로드 실패: {res.get('error')}")
        return RiggedHand.from_dict({
            k: v for k, v in res["result"].items()
            if k in {"object_name", "armature_name", "finger_chains",
                     "blendshapes", "handedness", "unit_scale"}
        })


def bake_procedural_asset(run_headless, out_obj: str, handedness: str = "right",
                          workdir: str = None) -> dict:
    """절차적 손을 OBJ 에셋으로 베이크. 에셋 임포트 파이프라인 검증/시드용."""
    res = run_headless({"op": "bake_hand_asset", "params": {
        "handedness": handedness, "unit_scale": 1000.0, "out_obj": out_obj}},
        workdir=workdir)
    if not res.get("ok"):
        raise RuntimeError(f"에셋 베이크 실패: {res.get('error')}")
    return res["result"]
