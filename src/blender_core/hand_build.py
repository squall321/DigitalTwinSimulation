# Blender Skin 모디파이어로 매끄러운 유기적 손(손바닥+5손가락)을 절차적 생성. bpy 전용.
# 외부 에셋/라이선스 없이 코드로 만들어 완전 포터블. 마디 뼈대(정점+엣지)에 skin+subsurf로
# 연속적인 손가락을 만들고, 관절 위치에 named 본을 두어 자동가중치로 바인딩한다.
import bmesh
import bpy
from mathutils import Vector

# 손 해부학 정의 (오른손 기준, mm — 폰 .k 좌표가 mm라 직접 정렬).
# 척추: 손목 → 손바닥하부 → 너클베이스. 손바닥은 넓은 반경으로 벌크를 만든다.
WRIST = (0.0, -28.0, 0.0, 15.0)
PALM_LOW = (0.0, 10.0, 0.0, 22.0)
PALM_TOP = (0.0, 50.0, 0.0, 24.0)

# 각 손가락 4관절: (x, y, z, skin반경). 첫 관절=너클, 마지막=손끝.
FINGERS = {
    "index":  [(-22, 62, 0, 8.5), (-22, 100, 0, 7.5), (-22, 126, -3, 6.0), (-22, 146, -6, 4.3)],
    "middle": [(-2, 64, 0, 9.0), (-2, 108, 0, 8.0), (-2, 137, -3, 6.5), (-2, 160, -6, 4.5)],
    "ring":   [(18, 62, 0, 8.5), (18, 100, 0, 7.5), (18, 126, -3, 6.0), (18, 146, -6, 4.3)],
    "pinky":  [(34, 56, 0, 7.5), (34, 84, 0, 6.5), (34, 104, -3, 5.0), (34, 120, -6, 3.6)],
}
# 엄지: 손바닥 하부 측면에서 나와 가로지르며 마주본다.
THUMB = [(-26, 2, 6, 11.0), (-44, 16, 11, 8.5), (-56, 32, 14, 6.0), (-64, 48, 14, 4.3)]

JOINT_NAMES = ["01", "02", "03"]     # 근위/중위/원위


def _mirror(pt, sign):
    """x를 handedness 부호로 반전(왼손 처리). pt=(x,y,z,...)."""
    return (pt[0] * sign,) + tuple(pt[1:])


def _build_skin_mesh(handedness):
    """마디 뼈대에 Skin+Subsurf로 연속적 손 메쉬를 만든다(모디파이어 적용 후 반환)."""
    sign = 1.0 if handedness == "right" else -1.0
    mesh = bpy.data.meshes.new("Hand")
    obj = bpy.data.objects.new("Hand", mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()

    wrist = _mirror(WRIST, sign)
    palm_low = _mirror(PALM_LOW, sign)
    palm_top = _mirror(PALM_TOP, sign)

    def add(pt):
        return bm.verts.new(pt[:3])

    vw, vl, vt = add(wrist), add(palm_low), add(palm_top)
    bm.edges.new([vw, vl])
    bm.edges.new([vl, vt])

    radius_by_co = {}

    def record(pt):
        radius_by_co[tuple(round(c, 1) for c in pt[:3])] = pt[3]

    for pt in (wrist, palm_low, palm_top):
        record(pt)

    # 손가락: 너클베이스(palm_top)에서 분기
    for chain in FINGERS.values():
        prev = vt
        for raw in chain:
            pt = _mirror(raw, sign)
            v = add(pt)
            bm.edges.new([prev, v])
            record(pt)
            prev = v
    # 엄지: 손바닥 하부에서 분기
    prev = vl
    for raw in THUMB:
        pt = _mirror(raw, sign)
        v = add(pt)
        bm.edges.new([prev, v])
        record(pt)
        prev = v

    bm.to_mesh(mesh)
    bm.free()

    obj.modifiers.new("Skin", 'SKIN')
    sl = mesh.skin_vertices[0].data
    for i, v in enumerate(mesh.vertices):
        r = radius_by_co.get(tuple(round(c, 1) for c in v.co), 7.0)
        sl[i].radius = (r, r)
    sl[0].use_root = True
    obj.modifiers.new("Sub", 'SUBSURF').levels = 2

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier="Skin")
    bpy.ops.object.modifier_apply(modifier="Sub")
    for p in mesh.polygons:
        p.use_smooth = True
    return obj


def _build_armature(handedness):
    """관절 위치에 named 본을 두고 finger_chains를 반환한다."""
    sign = 1.0 if handedness == "right" else -1.0
    arm_data = bpy.data.armatures.new("HandRig")
    arm = bpy.data.objects.new("HandRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones

    palm = eb.new("palm")
    palm.head = _mirror(WRIST, sign)[:3]
    palm.tail = _mirror(PALM_TOP, sign)[:3]

    chains = {}
    for name, chain in list(FINGERS.items()) + [("thumb", THUMB)]:
        bones = []
        parent = palm
        connect = False
        for i in range(len(chain) - 1):
            b = eb.new(f"{name}_{JOINT_NAMES[i]}")
            b.head = _mirror(chain[i], sign)[:3]
            b.tail = _mirror(chain[i + 1], sign)[:3]
            b.parent = parent
            b.use_connect = connect
            parent = b
            connect = True
            bones.append(b.name)
        chains[name] = bones
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm, chains


def _bind(obj, arm):
    """메쉬를 armature에 자동가중치로 바인딩(연속 손가락이 매끄럽게 휜다)."""
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    arm.select_set(True)
    bpy.context.view_layer.objects.active = arm
    try:
        bpy.ops.object.parent_set(type='ARMATURE_AUTO')
    except RuntimeError:
        mod = obj.modifiers.new("Armature", 'ARMATURE')
        mod.object = arm
        obj.parent = arm


def _add_blendshapes(hand):
    """계약 유지용 셰이프키(그립은 본 회전이 담당, 셰이프키는 미세보정 핸들)."""
    hand.shape_key_add(name="Basis")
    fist = hand.shape_key_add(name="fist")
    spread = hand.shape_key_add(name="spread")
    return {"fist": fist.name, "spread": spread.name}


def build_hand(handedness="right", unit_scale=1.0):
    """리깅된 매끄러운 손을 생성하고 RiggedHand 직렬화 dict를 반환한다.

    Skin 모디파이어 기반 연속 손가락 + 관절별 named 본 + 자동가중치.
    반환 dict는 hand/types.py RiggedHand.from_dict 와 호환.
    """
    obj = _build_skin_mesh(handedness)
    arm, chains = _build_armature(handedness)
    _bind(obj, arm)
    blendshapes = _add_blendshapes(obj)

    # 손은 mm로 정의(폰 .k와 동일 스케일). unit_scale=1000이면 그대로(호환), 그 외는
    # armature에만 스케일 적용(자식 메쉬는 상속 — 이중 transform_apply 금지).
    extra = unit_scale / 1000.0
    if abs(extra - 1.0) > 1e-9:
        arm.scale = (extra, extra, extra)
        bpy.context.view_layer.update()

    return {
        "object_name": obj.name,
        "armature_name": arm.name,
        "finger_chains": chains,
        "blendshapes": blendshapes,
        "handedness": handedness,
        "unit_scale": unit_scale,
    }
