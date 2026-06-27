# 절차적 손 로더. Blender headless로 손을 생성하고 RiggedHand 계약을 돌려준다.
# MakeHuman 대신 코드 생성 — 완전 포터블, CC0 무관(context-notes 참조).
from hand.types import RiggedHand


class ProceduralHandBuilder:
    """Blender API로 리깅 손을 생성하는 로더.

    추후 더 사실적인 손이 필요하면 OBJ/FBX 임포트 로더를 클래스 하나로 추가한다(YAGNI).
    인터페이스 계약(RiggedHand)은 동일하게 유지.
    """

    def __init__(self, handedness: str = "right", unit_scale: float = 1000.0):
        self.handedness = handedness
        self.unit_scale = unit_scale

    def build(self, run_headless, workdir: str = None, export_stl: str = None) -> RiggedHand:
        """run_headless 콜러블을 받아 Blender에서 손을 만든다(의존성 주입 → 테스트 용이)."""
        cmd = {
            "op": "build_hand",
            "params": {
                "handedness": self.handedness,
                "unit_scale": self.unit_scale,
                "export_stl": export_stl,
            },
        }
        res = run_headless(cmd, workdir=workdir)
        if not res.get("ok"):
            raise RuntimeError(f"손 생성 실패: {res.get('error')}\n{res.get('trace', '')}")
        return RiggedHand.from_dict({
            k: v for k, v in res["result"].items()
            if k in {"object_name", "armature_name", "finger_chains",
                     "blendshapes", "handedness", "unit_scale"}
        })
