# 손이 폰을 쥐는 그립 포즈를 만든다. bpy 전용.
# DESIGN 결정: 자동수렴 IK가 아니라 blendshape/본회전 프리셋 + per-finger shrinkwrap 1패스 + 관통 리포트.
import bpy
import math
from mathutils import Vector

# 그립 스타일별 굴곡 프리셋. 핵심 개선(승자 접근 A): 손가락별 차등 굴곡.
# 근위(prox)에서 ~90도 가까이 꺾어 가까운 긴모서리를 넘기고, 중/원위로 앞면을 따라 말려
# C자 감쌈을 만든다. spread는 근위 본 Z축 — 네 손가락이 부채꼴로 벌어진다.
# per_finger: {finger: [prox, mid, dist]}, spread: {finger: z}, thumb: [(rx,rz)*3].
# 얇은 폰(8mm)을 손바닥에 얹어 쥐는 자세. 손가락은 주먹처럼 꽉 굽지 않고 컵처럼
# 살짝 굽어 폰 표면에 얹힌다(강한 굴곡은 얇은 폰을 지나쳐버림 — 실측으로 확인).
GRIP_PRESETS = {
    "natural": {
        "per_finger": {
            "index":  [0.5, 0.6, 0.45],
            "middle": [0.5, 0.6, 0.45],
            "ring":   [0.52, 0.6, 0.45],
            "pinky":  [0.55, 0.55, 0.4],
        },
        "spread": {"index": 0.12, "middle": 0.0, "ring": -0.12, "pinky": -0.24},
        # 엄지: 폰 반대 모서리를 마주 잡는다(rx 세워 올리고 rz로 가로질러).
        "thumb": [(0.75, -0.6), (0.25, -0.5), (0.15, -0.4)],
    },
    "tight": {
        "per_finger": {
            "index":  [0.7, 0.8, 0.55],
            "middle": [0.7, 0.8, 0.55],
            "ring":   [0.72, 0.8, 0.55],
            "pinky":  [0.75, 0.75, 0.5],
        },
        "spread": {"index": 0.08, "middle": 0.0, "ring": -0.08, "pinky": -0.18},
        "thumb": [(0.9, -0.65), (0.35, -0.55), (0.2, -0.45)],
    },
    # pinch: 엄지+검지로 폰 모서리를 집고 나머지는 편다.
    "pinch": {
        "per_finger": {
            "index":  [0.6, 0.7, 0.5],
            "middle": [0.25, 0.2, 0.1],
            "ring":   [0.2, 0.15, 0.1],
            "pinky":  [0.15, 0.1, 0.05],
        },
        "spread": {"index": 0.2, "middle": 0.1, "ring": -0.05, "pinky": -0.15},
        "thumb": [(0.85, -0.7), (0.4, -0.6), (0.25, -0.5)],
    },
    # edge_hold: 손끝만 폰 모서리에 얕게. 손바닥은 덜 닿음.
    "edge_hold": {
        "per_finger": {
            "index":  [0.3, 0.4, 0.5],
            "middle": [0.3, 0.4, 0.5],
            "ring":   [0.32, 0.4, 0.5],
            "pinky":  [0.35, 0.38, 0.45],
        },
        "spread": {"index": 0.1, "middle": 0.0, "ring": -0.1, "pinky": -0.2},
        "thumb": [(0.55, -0.5), (0.2, -0.45), (0.12, -0.38)],
    },
    # loose: 아주 느슨하게 폰을 얹은 자세.
    "loose": {
        "per_finger": {
            "index":  [0.35, 0.4, 0.3],
            "middle": [0.35, 0.4, 0.3],
            "ring":   [0.37, 0.4, 0.3],
            "pinky":  [0.4, 0.38, 0.28],
        },
        "spread": {"index": 0.15, "middle": 0.0, "ring": -0.15, "pinky": -0.28},
        "thumb": [(0.6, -0.55), (0.2, -0.5), (0.12, -0.4)],
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


def measure_penetration(hand_name: str, phone_name: str, contact_tol: float = 3.0) -> dict:
    """손과 폰의 접촉/관통을 BVH로 측정.

    관통(penetration): 손 정점이 폰 내부에 있는 깊이(shrinkwrap OUTSIDE면 보통 0).
    접촉(contact): 손 정점이 폰 표면에서 contact_tol(mm) 이내에 있는 정도. shrinkwrap이
      표면 바깥에 앉히므로 "관통 0"이어도 접촉은 있다 → 그립 밀착도의 실제 지표.

    반환:
      max_penetration, penetrating_verts (기존 호환),
      contact_verts: 접촉 정점 수,
      contact_ratio: 접촉 정점 / 전체 손 정점 (0~1, 그립 밀착도),
      mean_gap: 접촉 정점들의 평균 표면 거리(mm, 작을수록 밀착).
    """
    from mathutils.bvhtree import BVHTree
    hand = bpy.data.objects[hand_name]
    phone = bpy.data.objects[phone_name]

    deps = bpy.context.evaluated_depsgraph_get()
    hand_eval = hand.evaluated_get(deps)
    hand_mesh = hand_eval.to_mesh()

    phone_bvh = BVHTree.FromObject(phone, deps)

    mw = hand.matrix_world
    pinv = phone.matrix_world.inverted()
    max_pen = 0.0
    n_pen = 0
    n_contact = 0
    gap_sum = 0.0
    min_gap = float("inf")
    n_total = len(hand_mesh.vertices)
    for v in hand_mesh.vertices:
        wco = mw @ v.co
        local = pinv @ wco
        loc, nor, idx, dist = phone_bvh.find_nearest(local)
        if loc is not None:
            d = (Vector(local) - Vector(loc)).length
            min_gap = min(min_gap, d)
            if (Vector(local) - Vector(loc)).dot(nor) < 0:      # 폰 내부(관통)
                max_pen = max(max_pen, d)
                n_pen += 1
            if d <= contact_tol:                                 # 표면 근처(접촉)
                n_contact += 1
                gap_sum += d
    hand_eval.to_mesh_clear()

    result = {
        "max_penetration": round(max_pen, 4),
        "penetrating_verts": n_pen,
        "contact_verts": n_contact,
        "contact_ratio": round(n_contact / n_total, 4) if n_total else 0.0,
        "mean_gap": round(gap_sum / n_contact, 4) if n_contact else 0.0,
        "min_gap": round(min_gap, 4) if min_gap != float("inf") else None,
    }
    # 정직한 진단: 접촉이 거의 없으면 그립이 밀착되지 않은 것(shrinkwrap 부족/손·폰 크기 불일치).
    if n_contact < n_total * 0.02:
        result["contact_warning"] = (
            f"손-폰 접촉 미약(접촉정점 {n_contact}, 최소갭 {result['min_gap']}mm). "
            "그립이 표면에 밀착되지 않음 — shrinkwrap offset을 줄이거나 손 크기/위치를 조정하세요."
        )
    return result


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
