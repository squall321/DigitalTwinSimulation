# 손 로더가 그립 단계에 제공하는 공통 계약. 값 타입을 고정해 독립 구현 충돌을 막는다.
from dataclasses import dataclass, field


@dataclass
class RiggedHand:
    """리깅된 손의 논리 핸들. bpy 객체 자체가 아니라 이름/구조만 담는다(프로세스 경계 JSON 가능).

    finger_chains: {"index": [root→tip 본 이름]}  — IK/포즈가 회전시킬 본 순서
    blendshapes:   {"fist": shape_key_이름, "spread": ...}  — 그립 프리셋이 구동할 셰이프키
    """

    object_name: str                                    # bpy.data.objects 키 (스킨 메쉬)
    armature_name: str                                  # bpy.data.objects 키 (armature)
    finger_chains: dict = field(default_factory=dict)
    blendshapes: dict = field(default_factory=dict)
    handedness: str = "right"
    unit_scale: float = 1.0                             # 손 좌표 → 타겟(mm) 정규화 배수

    def to_dict(self) -> dict:
        return {
            "object_name": self.object_name,
            "armature_name": self.armature_name,
            "finger_chains": self.finger_chains,
            "blendshapes": self.blendshapes,
            "handedness": self.handedness,
            "unit_scale": self.unit_scale,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "RiggedHand":
        return cls(**d)
