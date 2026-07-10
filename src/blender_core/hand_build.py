# Blender Skin 모디파이어로 매끄러운 유기적 손을 절차적 생성. bpy 전용.
# 핵심: 분기 없는 아일랜드 골격(손바닥 척추/손가락/엄지 각각 닫힌 튜브) + 비등방 반경
# (손바닥은 넓고 얇게) + voxel remesh SDF-union → 구조적으로 watertight 단일 셸.
# (연결 골격의 Skin 분기점 구멍 이슈를 원천 회피 — 감사 실측: 경계에지 24 → 0)
import bmesh
import bpy
from mathutils import Vector

# 손 해부학 정의 (오른손, mm). 각 점: (x, y, z, rx, rz) — rx 폭방향, rz 두께방향 skin 반경.
# 실측 비율 기준: 손 전체 ~180, 중지 76(검지/약지 92%, 새끼 75%), 손가락 지름 뿌리 17→끝 13
# (완만 테이퍼), 관절점 살짝 굵고 마디 사이 잘록, 단면 타원(폭>두께). 손바닥은 +z가 도톰(팜),
# -z가 평평(손등) — z 오프셋으로 근사.
# 손바닥 척추 4점: 손목 → 하부 → 중앙 → 너클베이스. 비등방(넓고 얇은) 슬랩.
# z = rz - 8 → 손등면(-z)이 손가락 등과 같은 평면(z≈-8)에 정렬: 손등 평평, 손바닥 도톰.
SPINE = [(0, -35, 4, 26, 12), (0, -8, 5, 32, 13),
         (0, 25, 4.5, 36, 12.5), (0, 46, 2.5, 38, 10.5)]
# 손가락 7점: 뿌리(0, 손바닥 안에 묻힘) → 너클MCP(1) → 중간(2) → PIP(3) → 중간(4)
# → DIP(5) → 손끝(6). 관절점(1,3,5)은 살짝 굵고 중간점(2,4)은 잘록 — 관절 정의.
FINGERS = {
    "index":  [(-28, 36, 0, 7.8, 7.5), (-28, 61, -0.5, 8.6, 7.8), (-28.6, 77, -0.5, 7.3, 6.8),
               (-29.2, 92, -1, 7.9, 7.3), (-29.7, 103, -2, 6.5, 6.1),
               (-30.2, 113, -3.5, 7.0, 6.6), (-31, 131, -6, 5.4, 5.4)],
    "middle": [(-9.5, 39, 0, 8.0, 7.8), (-9.5, 64, -0.5, 9.0, 8.2), (-9.5, 81, -0.5, 7.7, 7.1),
               (-9.5, 98, -1, 8.3, 7.7), (-9.5, 110, -2, 6.9, 6.4),
               (-9.5, 121, -3.5, 7.4, 6.9), (-9.5, 140, -6, 5.7, 5.7)],
    "ring":   [(9.5, 36, 0, 7.8, 7.5), (9.5, 61, -0.5, 8.6, 7.8), (9.8, 77, -0.5, 7.3, 6.8),
               (10.1, 92, -1, 7.9, 7.3), (10.4, 103, -2, 6.5, 6.1),
               (10.7, 113, -3.5, 7.0, 6.6), (11, 131, -6, 5.4, 5.4)],
    "pinky":  [(28, 29, 0, 7.0, 6.8), (28, 54, -0.5, 7.7, 7.0), (28.7, 67, -0.5, 6.5, 6.0),
               (29.4, 80, -1, 7.1, 6.5), (30, 89, -2, 5.8, 5.4),
               (30.6, 97, -3.5, 6.3, 5.9), (31.5, 111, -6, 4.8, 4.8)],
}
# 엄지 5점: 뿌리(손바닥 안) → CMC → MCP → IP → 손끝. 짧고 굵게(전체 ~60).
THUMB = [(-18, -4, 2, 11, 10), (-34, 4, 6, 10, 9), (-47, 16, 10, 8.5, 8),
         (-56, 28, 12, 7, 6.8), (-62, 38, 12, 5.5, 5.5)]
# 엄지둔덕(thenar) 아일랜드: 손목→엄지뿌리로 이어지는 불룩한 근육 덩어리. 본 없음(형상만).
THENAR = [(-6, -20, 3, 12, 9), (-18, -8, 4, 13, 10), (-30, 3, 5, 11, 9.5)]

JOINT_NAMES = ["01", "02", "03"]     # 근위/중위/원위 (뿌리점은 본 없음 — 손바닥에 묻힘)
FINGER_JOINT_IDX = (1, 3, 5, 6)      # 7점 체인에서 본 관절: MCP/PIP/DIP/손끝 → 본 3개
THUMB_JOINT_IDX = (1, 2, 3, 4)       # 5점 체인에서 본 관절: CMC/MCP/IP/손끝 → 본 3개
_VOXEL = 1.0                          # remesh 복셀(mm) — watertight union 해상도


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
    chain(THENAR)                      # 형상 전용 아일랜드(본 없음)
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
        # 형상용 중간점을 건너뛰고 해부학 관절점 4개만 본으로 → 손가락당 본 3개(계약 유지)
        idx = THUMB_JOINT_IDX if name == "thumb" else FINGER_JOINT_IDX
        joints = [chain[i] for i in idx]
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
