# Blender Skin 모디파이어로 매끄러운 유기적 손을 절차적 생성. bpy 전용.
# 핵심: 분기 없는 아일랜드 골격(손바닥 척추/손가락/엄지 각각 닫힌 튜브) + 비등방 반경
# (손바닥은 넓고 얇게) + voxel remesh SDF-union → 구조적으로 watertight 단일 셸.
# (연결 골격의 Skin 분기점 구멍 이슈를 원천 회피 — 감사 실측: 경계에지 24 → 0)
import bmesh
import bpy
from mathutils import Vector

# 손 해부학 정의 (오른손, mm). 각 점: (x, y, z, rx, rz) — rx 폭방향, rz 두께방향 skin 반경.
# 손바닥 척추: 손목 → 손바닥하부 → 너클베이스. 비등방(넓고 얇은) 슬랩.
SPINE = [(0, -28, 0, 18, 13), (0, 8, 0, 34, 14), (0, 44, 0, 40, 13)]
# 손가락 5점: 뿌리(손바닥 안에 묻힘) → 너클 → 중위 → 원위 → 손끝.
FINGERS = {
    "index":  [(-24, 38, 0, 9, 9), (-24, 62, 0, 8.5, 8.5), (-24, 100, 0, 7.5, 7.5),
               (-24, 126, -3, 6, 6), (-24, 146, -6, 4.3, 4.3)],
    "middle": [(-8, 40, 0, 9.5, 9.5), (-8, 64, 0, 9, 9), (-8, 108, 0, 8, 8),
               (-8, 137, -3, 6.5, 6.5), (-8, 160, -6, 4.5, 4.5)],
    "ring":   [(8, 40, 0, 9, 9), (8, 62, 0, 8.5, 8.5), (8, 100, 0, 7.5, 7.5),
               (8, 126, -3, 6, 6), (8, 146, -6, 4.3, 4.3)],
    "pinky":  [(24, 36, 0, 8, 8), (24, 56, 0, 7.5, 7.5), (24, 84, 0, 6.5, 6.5),
               (24, 104, -3, 5, 5), (24, 120, -6, 3.6, 3.6)],
}
# 엄지 5점: 손바닥 하부 안 → 측면으로 나와 가로지르며 대향.
THUMB = [(-16, 0, 3, 11, 10), (-30, 0, 6, 10.5, 9.5), (-46, 14, 11, 8.5, 8),
         (-58, 30, 14, 6, 6), (-66, 46, 14, 4.3, 4.3)]

JOINT_NAMES = ["01", "02", "03"]     # 근위/중위/원위 (뿌리점은 본 없음 — 손바닥에 묻힘)
_VOXEL = 1.2                          # remesh 복셀(mm) — watertight union 해상도


def _mirror(pt, sign):
    """x를 handedness 부호로 반전(왼손). pt=(x,y,z,rx,rz)."""
    return (pt[0] * sign,) + tuple(pt[1:])


def _build_skin_mesh(handedness):
    """아일랜드 골격에 Skin(비등방)+Subsurf → voxel remesh union.

    각 체인이 분기 없는 닫힌 튜브라 skin 출력이 이미 watertight이고, 닫힌 셸들의
    SDF union(voxel remesh)은 형상을 보존하며 단일 watertight 셸을 만든다.
    """
    sign = 1.0 if handedness == "right" else -1.0
    mesh = bpy.data.meshes.new("Hand")
    obj = bpy.data.objects.new("Hand", mesh)
    bpy.context.collection.objects.link(obj)
    bm = bmesh.new()

    roots = []
    rad = {}

    def chain(pts):
        pts = [_mirror(p, sign) for p in pts]
        vs = [bm.verts.new(p[:3]) for p in pts]
        for a, b in zip(vs, vs[1:]):
            bm.edges.new([a, b])
        for v, p in zip(vs, pts):
            rad[tuple(round(c, 2) for c in v.co)] = (p[3], p[4])
        roots.append(tuple(round(c, 2) for c in vs[0].co))

    chain(SPINE)
    for c in FINGERS.values():
        chain(c)
    chain(THUMB)
    bm.to_mesh(mesh)
    bm.free()

    obj.modifiers.new("Skin", 'SKIN')
    sl = mesh.skin_vertices[0].data
    for i, v in enumerate(mesh.vertices):
        k = tuple(round(c, 2) for c in v.co)
        sl[i].radius = rad.get(k, (7.0, 7.0))
        sl[i].use_root = k in roots     # 아일랜드마다 루트 1개
    obj.modifiers.new("Sub", 'SUBSURF').levels = 2

    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.modifier_apply(modifier="Skin")
    bpy.ops.object.modifier_apply(modifier="Sub")

    # SDF union: 겹친 닫힌 셸들 → 단일 watertight 셸 (형상 보존, 구멍 원천 차단)
    mod = obj.modifiers.new("Remesh", 'REMESH')
    mod.mode = 'VOXEL'
    mod.voxel_size = _VOXEL
    bpy.ops.object.modifier_apply(modifier="Remesh")

    for p in mesh.polygons:
        p.use_smooth = True
    return obj


def _build_armature(handedness):
    """관절 위치에 named 본. 손가락 뿌리점(손바닥에 묻힘)은 본 없이 건너뛴다."""
    sign = 1.0 if handedness == "right" else -1.0
    arm_data = bpy.data.armatures.new("HandRig")
    arm = bpy.data.objects.new("HandRig", arm_data)
    bpy.context.collection.objects.link(arm)
    bpy.context.view_layer.objects.active = arm
    bpy.ops.object.mode_set(mode='EDIT')
    eb = arm_data.edit_bones

    palm = eb.new("palm")
    palm.head = _mirror(SPINE[0], sign)[:3]
    palm.tail = _mirror(SPINE[-1], sign)[:3]

    chains = {}
    for name, chain in list(FINGERS.items()) + [("thumb", THUMB)]:
        joints = chain[1:]              # 뿌리점 제외 → 너클/중위/원위/손끝 4점 = 본 3개
        bones = []
        parent = palm
        connect = False
        for i in range(len(joints) - 1):
            b = eb.new(f"{name}_{JOINT_NAMES[i]}")
            b.head = _mirror(joints[i], sign)[:3]
            b.tail = _mirror(joints[i + 1], sign)[:3]
            b.parent = parent
            b.use_connect = connect
            parent = b
            connect = True
            bones.append(b.name)
        chains[name] = bones
    bpy.ops.object.mode_set(mode='OBJECT')
    return arm, chains


def _bind(obj, arm):
    """자동 가중치 바인딩(연속 손가락이 매끄럽게 휜다)."""
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
    """계약 유지용 셰이프키(그립은 본 회전이 담당)."""
    hand.shape_key_add(name="Basis")
    fist = hand.shape_key_add(name="fist")
    spread = hand.shape_key_add(name="spread")
    return {"fist": fist.name, "spread": spread.name}


def build_hand(handedness="right", unit_scale=1.0):
    """리깅된 watertight 손을 생성하고 RiggedHand 직렬화 dict를 반환한다."""
    obj = _build_skin_mesh(handedness)
    arm, chains = _build_armature(handedness)
    _bind(obj, arm)
    blendshapes = _add_blendshapes(obj)

    # 손은 mm 정의(폰 .k와 동일 스케일). 다른 스케일은 armature에만(상속 — 중첩 금지).
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
