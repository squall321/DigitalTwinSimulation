# Blender API로 리깅된 손(손바닥+5손가락 3관절)을 절차적 생성. bpy 전용.
# 외부 에셋/라이선스 없이 코드로 손을 만들어 완전 포터블하게 한다.
import bpy
from mathutils import Vector

# 손 해부학 정의 (오른손 기준, 단위 mm — 폰(.k 좌표)이 mm 스케일이라 직접 정렬).
# 각 손가락: (뿌리 x위치, 뿌리 y위치, [근위/중위/원위 마디 길이], 굵기)
# 엄지는 손바닥 측면에서 비스듬히 난다.
FINGERS = {
    # name:     base_x, base_y, segs(len*3),        radius
    "thumb":  (-35.0,  20.0, [30.0, 25.0, 20.0],   11.0),
    "index":  (-18.0,  90.0, [40.0, 26.0, 20.0],    9.0),
    "middle": (  0.0,  95.0, [45.0, 28.0, 22.0],    9.0),
    "ring":   ( 18.0,  90.0, [40.0, 26.0, 20.0],    9.0),
    "pinky":  ( 34.0,  80.0, [30.0, 20.0, 16.0],    8.0),
}
PALM_SIZE = (90.0, 95.0, 25.0)       # 폭, 길이, 두께 (mm)
JOINT_NAMES = ["01", "02", "03"]     # 근위/중위/원위


def _new_armature(name="HandRig"):
    arm_data = bpy.data.armatures.new(name)
    arm_obj = bpy.data.objects.new(name, arm_data)
    bpy.context.collection.objects.link(arm_obj)
    bpy.context.view_layer.objects.active = arm_obj
    return arm_obj, arm_data


def _build_bones(arm_data, handedness):
    """손가락별 본 체인을 만들고 finger_chains 맵을 돌려준다."""
    bpy.ops.object.mode_set(mode='EDIT')
    sign = 1.0 if handedness == "right" else -1.0
    chains = {}
    eb = arm_data.edit_bones
    for fname, (bx, by, seg_lens, _r) in FINGERS.items():
        chain = []
        y = by
        x = bx * sign
        parent = None
        for i, seglen in enumerate(seg_lens):
            bone = eb.new(f"{fname}_{JOINT_NAMES[i]}")
            bone.head = Vector((x, y, 0.0))
            bone.tail = Vector((x, y + seglen, 0.0))
            if parent:
                bone.parent = parent
                bone.use_connect = True
            parent = bone
            chain.append(bone.name)
            y += seglen
        chains[fname] = chain
    bpy.ops.object.mode_set(mode='OBJECT')
    return chains


def _build_palm_mesh():
    """손바닥 박스 메쉬."""
    w, l, t = PALM_SIZE
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=(0, l * 0.5 - 0.01, 0))
    palm = bpy.context.active_object
    palm.scale = (w * 0.5, l * 0.5, t * 0.5)
    bpy.ops.object.transform_apply(scale=True)
    palm.name = "Palm"
    return palm


def _build_finger_meshes(handedness):
    """손가락별 실린더 마디 메쉬 리스트."""
    sign = 1.0 if handedness == "right" else -1.0
    objs = []
    for fname, (bx, by, seg_lens, r) in FINGERS.items():
        y = by
        x = bx * sign
        for i, seglen in enumerate(seg_lens):
            bpy.ops.mesh.primitive_cylinder_add(
                radius=r, depth=seglen, vertices=12,
                location=(x, y + seglen * 0.5, 0.0),
            )
            seg = bpy.context.active_object
            # 실린더 축(Z)을 손가락 방향(Y)으로 회전
            seg.rotation_euler = (1.5707963, 0.0, 0.0)
            bpy.ops.object.transform_apply(rotation=True)
            seg.name = f"{fname}_seg{i}"
            objs.append(seg)
            y += seglen
    return objs


def _join_and_skin(meshes, arm_obj):
    """메쉬들을 하나로 합치고 armature에 스킨 바인딩(자동 가중치)."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    for m in meshes:
        m.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.join()
    hand = bpy.context.active_object
    hand.name = "Hand"
    # armature 모디파이어 + 자동 가중치
    arm_obj.select_set(True)
    hand.select_set(True)
    bpy.context.view_layer.objects.active = arm_obj
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    except RuntimeError:
        # 자동 가중치 실패 시 단순 모디파이어만(가중치 0 → 후처리)
        mod = hand.modifiers.new("Armature", 'ARMATURE')
        mod.object = arm_obj
    return hand


def _add_blendshapes(hand):
    """open(기준)·fist·spread 셰이프키. fist는 본 회전이 담당하나,
    셰이프키 핸들을 만들어 그립 프리셋이 미세 보정에 쓸 수 있게 한다."""
    hand.shape_key_add(name="Basis")
    fist = hand.shape_key_add(name="fist")
    spread = hand.shape_key_add(name="spread")
    return {"fist": fist.name, "spread": spread.name}


def build_hand(handedness="right", unit_scale=1.0):
    """리깅 손을 생성하고 RiggedHand 직렬화 dict를 반환한다.

    반환 dict는 hand/types.py RiggedHand.from_dict 와 호환.
    프로세스 경계(headless runner)를 JSON으로 넘기기 위해 dict로 돌려준다.
    """
    arm_obj, arm_data = _new_armature()
    chains = _build_bones(arm_data, handedness)
    palm = _build_palm_mesh()
    fingers = _build_finger_meshes(handedness)
    hand = _join_and_skin([palm] + fingers, arm_obj)
    blendshapes = _add_blendshapes(hand)

    # 손은 mm로 정의되어 있다(폰 .k 좌표와 동일 스케일). 추가 스케일이 필요하면
    # armature에만 적용하고 자식 메쉬는 부모 상속으로 따라간다 — 둘 다 transform_apply
    # 하면 스케일이 중첩 적용되므로 금지(과거 1000² 폭주 버그).
    extra = unit_scale / 1000.0   # 기존 호출이 1000(mm)을 넘기던 호환: mm 기준이므로 1.0
    if abs(extra - 1.0) > 1e-9:
        arm_obj.scale = (extra, extra, extra)
        bpy.context.view_layer.update()

    return {
        "object_name": hand.name,
        "armature_name": arm_obj.name,
        "finger_chains": chains,
        "blendshapes": blendshapes,
        "handedness": handedness,
        "unit_scale": unit_scale,
    }
