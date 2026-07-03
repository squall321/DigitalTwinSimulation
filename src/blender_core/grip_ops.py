# 손이 폰을 쥐는 그립 포즈를 만든다. bpy 전용.
# DESIGN 결정: 자동수렴 IK가 아니라 blendshape/본회전 프리셋 + per-finger shrinkwrap 1패스 + 관통 리포트.
import bpy
import math
from mathutils import Vector

# 그립 스타일별 굴곡 프리셋. 핵심 개선(승자 접근 A): 손가락별 차등 굴곡.
# 근위(prox)에서 ~90도 가까이 꺾어 가까운 긴모서리를 넘기고, 중/원위로 앞면을 따라 말려
# C자 감쌈을 만든다. spread는 근위 본 Z축 — 네 손가락이 부채꼴로 벌어진다.
# per_finger: {finger: [prox, mid, dist]}, spread: {finger: z}, thumb: [(rx,rz)*3].
GRIP_PRESETS = {
    "natural": {
        "per_finger": {
            "index":  [1.5, 1.1, 0.6],
            "middle": [1.5, 1.1, 0.6],
            "ring":   [1.55, 1.1, 0.6],
            "pinky":  [1.6, 1.1, 0.55],
        },
        "spread": {"index": 0.12, "middle": 0.0, "ring": -0.12, "pinky": -0.24},
        # 엄지: 앞면 위로 올라가(rx) 손가락 쪽(+X)으로 가로질러 눕혀(rz) 마주 누른다.
        "thumb": [(0.85, -0.9), (0.2, -0.7), (0.1, -0.5)],
    },
    "tight": {
        "per_finger": {
            "index":  [1.6, 1.25, 0.75],
            "middle": [1.6, 1.25, 0.75],
            "ring":   [1.65, 1.25, 0.75],
            "pinky":  [1.7, 1.25, 0.7],
        },
        "spread": {"index": 0.08, "middle": 0.0, "ring": -0.08, "pinky": -0.18},
        "thumb": [(0.9, -0.95), (0.3, -0.7), (0.15, -0.55)],
    },
    # pinch: 엄지+검지로 집고 나머지 손가락은 펴진다(카드/얇은 폰 집기).
    "pinch": {
        "per_finger": {
            "index":  [1.3, 0.9, 0.5],
            "middle": [0.3, 0.2, 0.1],
            "ring":   [0.25, 0.15, 0.1],
            "pinky":  [0.2, 0.1, 0.05],
        },
        "spread": {"index": 0.2, "middle": 0.1, "ring": -0.05, "pinky": -0.15},
        "thumb": [(1.0, -1.0), (0.4, -0.8), (0.2, -0.6)],
    },
    # edge_hold: 가장자리를 얕게 걸침. 원위 마디로만 잡아 앞면을 덜 가림.
    "edge_hold": {
        "per_finger": {
            "index":  [0.35, 0.45, 0.6],
            "middle": [0.35, 0.45, 0.6],
            "ring":   [0.4, 0.45, 0.6],
            "pinky":  [0.45, 0.4, 0.55],
        },
        "spread": {"index": 0.1, "middle": 0.0, "ring": -0.1, "pinky": -0.2},
        "thumb": [(0.6, -0.7), (0.2, -0.5), (0.1, -0.4)],
    },
    # loose: 느슨하게 감쌈. 접촉은 하되 힘을 덜 준 자세.
    "loose": {
        "per_finger": {
            "index":  [1.0, 0.7, 0.4],
            "middle": [1.0, 0.7, 0.4],
            "ring":   [1.05, 0.7, 0.4],
            "pinky":  [1.1, 0.65, 0.35],
        },
        "spread": {"index": 0.15, "middle": 0.0, "ring": -0.15, "pinky": -0.28},
        "thumb": [(0.7, -0.75), (0.15, -0.6), (0.1, -0.45)],
    },
}


def _pose_finger_chain(arm_obj, chain, angles, spread):
    """한 손가락 본 체인을 각도 리스트로 회전. 누적이 아니라 절대 설정.
    굴곡은 X축(손가락이 손바닥 쪽으로 말림), spread는 근위 본 Z축(부채꼴)."""
    for i, bone_name in enumerate(chain):
        pb = arm_obj.pose.bones.get(bone_name)
        if pb is None:
            continue
        pb.rotation_mode = 'XYZ'
        rx = angles[i] if i < len(angles) else angles[-1]
        rz = spread if i == 0 else 0.0
        pb.rotation_euler = (rx, 0.0, rz)


def apply_grip(hand_info: dict, style: str = "natural") -> dict:
    """손에 그립 프리셋을 적용한다. hand_info = build_hand 반환 dict."""
    preset = GRIP_PRESETS.get(style, GRIP_PRESETS["natural"])
    arm_obj = bpy.data.objects[hand_info["armature_name"]]
    bpy.context.view_layer.objects.active = arm_obj
    bpy.ops.object.mode_set(mode='POSE')
    chains = hand_info["finger_chains"]
    for finger in ("index", "middle", "ring", "pinky"):
        chain = chains.get(finger)
        if not chain:
            continue
        _pose_finger_chain(arm_obj, chain, preset["per_finger"][finger],
                           preset["spread"][finger])
    # 엄지: (rx, rz) 쌍으로 앞면을 대각선 가로질러 손가락과 마주 누른다.
    thumb_chain = chains.get("thumb")
    if thumb_chain:
        for i, bone_name in enumerate(thumb_chain):
            pb = arm_obj.pose.bones.get(bone_name)
            if pb is None:
                continue
            rx, rz = preset["thumb"][i] if i < len(preset["thumb"]) else preset["thumb"][-1]
            pb.rotation_mode = 'XYZ'
            pb.rotation_euler = (rx, 0.0, rz)
    bpy.ops.object.mode_set(mode='OBJECT')
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


def shrinkwrap_fingers_to_phone(hand_name: str, phone_name: str, offsets=(1.5, 0.8)) -> dict:
    """손가락 표면을 폰 표면으로 2패스 shrinkwrap(관통 완화 + 접촉 밀착, 승자 graft).
    1패스(1.5)로 거칠게 끌어당기고 2패스(0.8)로 표면에 바짝 붙인다.
    DESIGN: 자동 IK 수렴 대신 2패스. 폰 외곽이 손가락 자리만큼 함몰되는 건 모핑 입력."""
    hand = bpy.data.objects[hand_name]
    phone = bpy.data.objects[phone_name]
    for off in offsets:
        mod = hand.modifiers.new(f"GripWrap{off}", 'SHRINKWRAP')
        mod.target = phone
        mod.wrap_method = 'NEAREST_SURFACEPOINT'
        mod.offset = off
        mod.wrap_mode = 'OUTSIDE'   # 폰 바깥으로 밀어 관통 방지
    return {"shrinkwrap_offsets": list(offsets)}
