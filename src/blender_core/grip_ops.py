# 손이 폰을 쥐는 그립 포즈를 만든다. bpy 전용.
# DESIGN 결정: 자동수렴 IK가 아니라 blendshape/본회전 프리셋 + per-finger shrinkwrap 1패스 + 관통 리포트.
import bpy
import math
from mathutils import Vector

# 그립 스타일별 손가락 굴곡 프리셋 (각 관절 회전 라디안, 근위/중위/원위).
# 값은 "자연스러운 쥠"을 근사하는 데이터 — IK 수렴이 아니라 직접 지정.
GRIP_PRESETS = {
    "natural":  {"prox": 0.55, "mid": 0.70, "dist": 0.45, "thumb": 0.40, "spread": 0.0},
    "tight":    {"prox": 0.85, "mid": 1.00, "dist": 0.70, "thumb": 0.65, "spread": -0.1},
    "pinch":    {"prox": 0.30, "mid": 0.40, "dist": 0.30, "thumb": 0.80, "spread": 0.15},
    "edge_hold":{"prox": 0.35, "mid": 0.45, "dist": 0.55, "thumb": 0.30, "spread": 0.0},
    "flat_palm":{"prox": 0.05, "mid": 0.05, "dist": 0.05, "thumb": 0.10, "spread": 0.2},
}


def _pose_finger_chain(arm_obj, chain, preset, finger):
    """한 손가락 본 체인을 프리셋 각도로 회전. 누적이 아니라 절대 설정."""
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='POSE')
    is_thumb = (finger == "thumb")
    angles = (
        [preset["thumb"], preset["thumb"] * 0.7, preset["thumb"] * 0.5]
        if is_thumb else
        [preset["prox"], preset["mid"], preset["dist"]]
    )
    for i, bone_name in enumerate(chain):
        pb = arm_obj.pose.bones.get(bone_name)
        if pb is None:
            continue
        pb.rotation_mode = 'XYZ'
        # 굴곡은 X축 회전(손가락이 손바닥 쪽으로 말림). 근위 본에 spread를 Z축으로.
        rx = angles[i] if i < len(angles) else angles[-1]
        rz = preset.get("spread", 0.0) if i == 0 and not is_thumb else 0.0
        pb.rotation_euler = (rx, 0.0, rz)
    bpy.ops.object.mode_set(mode='OBJECT')


def apply_grip(hand_info: dict, style: str = "natural") -> dict:
    """손에 그립 프리셋을 적용한다. hand_info = build_hand 반환 dict."""
    preset = GRIP_PRESETS.get(style, GRIP_PRESETS["natural"])
    arm_obj = bpy.data.objects[hand_info["armature_name"]]
    for finger, chain in hand_info["finger_chains"].items():
        _pose_finger_chain(arm_obj, chain, preset, finger)
    bpy.context.view_layer.update()
    return {"style": style, "preset": preset}


def measure_penetration(hand_name: str, phone_name: str) -> dict:
    """손과 폰 표면의 관통량을 BVH로 측정. 관통 = 손 정점이 폰 내부에 있는 깊이."""
    from mathutils.bvhtree import BVHTree
    hand = bpy.data.objects[hand_name]
    phone = bpy.data.objects[phone_name]

    deps = bpy.context.evaluated_depsgraph_get()
    hand_eval = hand.evaluated_get(deps)
    hand_mesh = hand_eval.to_mesh()

    phone_eval = phone.evaluated_get(deps)
    phone_bvh = BVHTree.FromObject(phone, deps)

    mw = hand.matrix_world
    pinv = phone.matrix_world.inverted()
    max_pen = 0.0
    n_pen = 0
    for v in hand_mesh.vertices:
        wco = mw @ v.co
        local = pinv @ wco
        # ray casting으로 내부 판정(아래 방향 레이가 홀수번 교차하면 내부)
        loc, nor, idx, dist = phone_bvh.find_nearest(local)
        if loc is not None:
            d = (Vector(local) - Vector(loc)).length
            # 법선과 반대면 내부(관통)
            if (Vector(local) - Vector(loc)).dot(nor) < 0:
                max_pen = max(max_pen, d)
                n_pen += 1
    hand_eval.to_mesh_clear()
    return {"max_penetration": round(max_pen, 4), "penetrating_verts": n_pen}


def shrinkwrap_fingers_to_phone(hand_name: str, phone_name: str, offset: float = 0.5) -> dict:
    """손가락 표면을 폰 표면으로 1패스 shrinkwrap(관통 완화 + 접촉 밀착).
    DESIGN: 자동 IK 수렴 대신 단순 1패스. 폰 외곽이 손가락 자리만큼 함몰되는 건 모핑 입력."""
    hand = bpy.data.objects[hand_name]
    phone = bpy.data.objects[phone_name]
    mod = hand.modifiers.new("GripWrap", 'SHRINKWRAP')
    mod.target = phone
    mod.wrap_method = 'NEAREST_SURFACEPOINT'
    mod.offset = offset
    mod.wrap_mode = 'OUTSIDE'   # 폰 바깥으로 밀어 관통 방지
    return {"shrinkwrap_offset": offset}
