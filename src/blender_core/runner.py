# headless Blender 진입점: cmd.json을 받아 명령을 실행하고 result.json으로 결과 회수.
# MCP/app(py3.10)과 Blender(py3.11)의 프로세스 경계 — 주고받는 데이터는 순수 JSON dict만.
import bpy
import sys
import json
import os
import math
from mathutils import Vector

# Blender가 이 스크립트를 --python으로 실행할 때 src가 sys.path에 없을 수 있다.
# 자기 위치(src/blender_core/runner.py) 기준으로 src를 직접 추가한다(env PYTHONPATH에 의존하지 않음).
_SRC_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC_DIR not in sys.path:
    sys.path.insert(0, _SRC_DIR)


def _run(cmd: dict) -> dict:
    """단일 명령 디스패치. cmd = {"op": str, "params": {...}}."""
    op = cmd.get("op")
    params = cmd.get("params", {})

    bpy.ops.wm.read_factory_settings(use_empty=True)

    if op == "build_hand":
        from blender_core.hand_build import build_hand
        info = build_hand(
            handedness=params.get("handedness", "right"),
            unit_scale=params.get("unit_scale", 1.0),
        )
        out = params.get("export_stl")
        if out:
            _export_object_stl(info["object_name"], out)
            info["stl_path"] = out
            info["stl_bytes"] = os.path.getsize(out)
        obj_out = params.get("export_obj")
        if obj_out:
            _export_object_obj(info["object_name"], obj_out)
            info["obj_path"] = obj_out
        return {"ok": True, "result": info}

    if op == "bake_hand_asset":
        # 절차적 손을 OBJ 에셋으로 베이크(사실적 에셋 임포트 경로 검증용).
        from blender_core.hand_build import build_hand
        info = build_hand(handedness=params.get("handedness", "right"),
                          unit_scale=params.get("unit_scale", 1.0))
        _export_object_obj(info["object_name"], params["out_obj"])
        info["obj_path"] = params["out_obj"]
        info["obj_bytes"] = os.path.getsize(params["out_obj"])
        return {"ok": True, "result": info}

    if op == "import_hand_obj":
        return _import_hand_obj(params)

    if op == "grip_phone":
        return _grip_phone(params)

    return {"ok": False, "error": f"unknown op: {op}"}


def _import_hand_obj(params: dict) -> dict:
    """OBJ 손 에셋을 임포트한다. armature가 함께 있으면 그 본으로 finger_chains를
    추론하고, 없으면 메쉬만 로드(그립하려면 절차 스켈레톤 필요 → 진단으로 알림)."""
    import os
    asset = params["asset_path"]
    if not os.path.exists(asset):
        return {"ok": False, "error": f"에셋 없음: {asset}"}
    before = set(bpy.data.objects.keys())
    bpy.ops.wm.obj_import(filepath=asset)
    new = [n for n in bpy.data.objects.keys() if n not in before]
    meshes = [bpy.data.objects[n] for n in new if bpy.data.objects[n].type == 'MESH']
    arms = [bpy.data.objects[n] for n in new if bpy.data.objects[n].type == 'ARMATURE']
    if not meshes:
        return {"ok": False, "error": "임포트된 메쉬 없음"}
    hand = meshes[0]
    hand.name = "Hand"

    # 본 체인: 임포트 armature가 있으면 이름으로 추론, 없으면 빈 dict(그립 불가 경고).
    finger_chains = {}
    arm_name = ""
    if arms:
        arm = arms[0]
        arm_name = arm.name
        for finger in ("thumb", "index", "middle", "ring", "pinky"):
            chain = [b.name for b in arm.data.bones
                     if b.name.lower().startswith(finger)]
            if chain:
                finger_chains[finger] = chain

    info = {
        "object_name": hand.name,
        "armature_name": arm_name,
        "finger_chains": finger_chains,
        "blendshapes": {},
        "handedness": params.get("handedness", "right"),
        "unit_scale": 1.0,
        "vert_count": len(hand.data.vertices),
        "has_rig": bool(arms),
    }
    if not arms:
        info["warning"] = ("에셋에 armature 없음 → 그립 불가. 절차 스켈레톤에 "
                           "바인딩하거나 리깅된 에셋을 사용하세요.")
    out = params.get("export_stl")
    if out:
        _export_object_stl(hand.name, out)
        info["stl_path"] = out
    return {"ok": True, "result": info}


def _export_object_stl(obj_name: str, out_path: str):
    """단일 객체를 STL로 익스포트(모디파이어 적용)."""
    obj = bpy.data.objects[obj_name]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.stl_export(
        filepath=out_path, export_selected_objects=True, apply_modifiers=True
    )


def _export_object_obj(obj_name: str, out_path: str):
    """단일 객체를 OBJ 에셋으로 익스포트(모디파이어 적용). 손 에셋 베이크용."""
    obj = bpy.data.objects[obj_name]
    for o in bpy.context.selected_objects:
        o.select_set(False)
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.wm.obj_export(
        filepath=out_path, export_selected_objects=True, apply_modifiers=True
    )


def _grip_phone(params: dict) -> dict:
    """손 빌드 → 폰 STL 로드 → 위치맞춤 → 그립 프리셋 → shrinkwrap → 관통측정 →
    그립으로 함몰된 폰 외곽(phone_edited_outer.stl) 출력."""
    from blender_core.hand_build import build_hand
    from blender_core import grip_ops

    style = params.get("style", "natural")
    handedness = params.get("handedness", "right")
    phone_stl = params["phone_stl"]                 # 슬라이스1 산출 외곽 STL
    edited_out = params.get("edited_outer_stl")     # 그립 함몰 결과(모핑 입력)
    hand_out = params.get("hand_stl")

    # 1) 손 생성 (mm)
    hand_info = build_hand(handedness=handedness, unit_scale=1000.0)
    hand = bpy.data.objects[hand_info["object_name"]]
    arm = bpy.data.objects[hand_info["armature_name"]]

    # 2) 폰 로드
    bpy.ops.wm.stl_import(filepath=phone_stl)
    phone = bpy.context.active_object
    phone.name = "Phone"

    # 3) 위치맞춤 (전략 C — 세로 랜드스케이프 클램프 그립):
    #    손 전체를 z축 -90° 회전(arm_rot)시켜 손가락 배열축이 폰 너비(x)를 가로지르게 세운다.
    #    네 손가락이 폰의 한쪽 긴 모서리를 감싸 앞면으로 접혀 내리고, 엄지가 반대 앞면을 눌러
    #    폰을 손바닥/엄지와 손가락 사이에 클램프한다(트레이에 얹은 게 아니라 감쌈).
    #    폰 중심 기준 오프셋(arm_offset)으로 일반화 — 폰 크기와 무관. arm_rot/arm_offset로 override.
    #    arm.location은 world 좌표. _deform_phone_by_grip/measure_penetration은 matrix_world로
    #    회전을 정확히 반영한다.
    pbb = [phone.matrix_world @ Vector(c) for c in phone.bound_box]
    pmin = Vector((min(v.x for v in pbb), min(v.y for v in pbb), min(v.z for v in pbb)))
    pmax = Vector((max(v.x for v in pbb), max(v.y for v in pbb), max(v.z for v in pbb)))
    center = (pmin + pmax) * 0.5
    arm_offset = params.get("arm_offset", [-18.0, -9.0, -28.0])  # 폰 중심 기준 world 오프셋
    arm_rot = params.get("arm_rot", [0.0, 0.0, -math.pi / 2])    # 손 전체 회전(z축 -90°)
    arm.location = (
        center.x + arm_offset[0],
        center.y + arm_offset[1],
        center.z + arm_offset[2],
    )
    arm.rotation_euler = tuple(arm_rot)
    bpy.context.view_layer.update()

    # 4) 그립 프리셋 적용
    grip_meta = grip_ops.apply_grip(hand_info, style=style)
    bpy.context.view_layer.update()
    # (shrinkwrap 제거: 손 메쉬를 왜곡시켜 아티팩트 유발. 포즈만으로 자연스럽고,
    #  폰 함몰은 아래 _deform_phone_by_grip이 담당한다.)

    # 5) 접촉 해소: 고정 프리셋은 손가락/엄지를 폰 속으로 통과시킨다(사용자 지적).
    #    손가락별 굴곡을 이분탐색으로 줄여 표면에 '닿되 파고들지 않게'(관통 ≤ tol).
    contact_tol = params.get("contact_resolve_tol", 0.5)
    contact = grip_ops.resolve_finger_contact(
        hand_info, phone.name, grip_meta["preset"], tol=contact_tol)

    # 6) 관통 측정 (해소 후 — tol 근처여야 정상)
    pen = grip_ops.measure_penetration(hand.name, phone.name)

    # 7) 그립 자국을 폰 표면에 실제로 찍는다: 손이 누르는 곳에서 폰을 안쪽으로 함몰.
    #    이 함몰된 외곽이 슬라이스4 모핑의 입력 → 재해석 가능한 .k에 그립 자국이 남는다.
    press = params.get("press_depth", 2.5)
    reach = params.get("contact_range", 5.0)
    dent_info = _deform_phone_by_grip(hand, phone, press_depth=press, contact_range=reach)

    result = {
        "hand": hand_info, "style": style, "penetration": pen, "grip_meta": grip_meta,
        "contact_resolve": contact,
        "phone_bbox": {"min": list(pmin), "max": list(pmax)}, "dent": dent_info,
    }
    if hand_out:
        _export_object_stl(hand.name, hand_out)
        result["hand_stl"] = hand_out
    if edited_out:
        _export_object_stl(phone.name, edited_out)   # 이제 함몰된 폰이 나간다
        result["edited_outer_stl"] = edited_out
    return {"ok": True, "result": result}


def _deform_phone_by_grip(hand, phone, press_depth=2.5, contact_range=5.0):
    """손이 누르는 곳에서 폰 표면을 안쪽으로 함몰시킨다(그립 자국 → 모핑 입력).

    손을 몰드로 사용: 각 폰 정점에서 가장 가까운 손 표면점을 찾아, 손이 폰 바깥쪽에서
    contact_range 이내로 다가와 있으면 그 정점을 폰 안쪽으로 밀어 넣는다(거리 기반 감쇠).
    world 좌표로 계산(손은 armature로 이동돼 world 행렬이 항등 아님).
    """
    from mathutils.bvhtree import BVHTree
    deps = bpy.context.evaluated_depsgraph_get()

    # 손 표면 BVH를 world 좌표로 구성
    he = hand.evaluated_get(deps)
    hm = he.to_mesh()
    mw_h = hand.matrix_world
    hverts = [mw_h @ v.co for v in hm.vertices]
    hpolys = [tuple(p.vertices) for p in hm.polygons]
    hand_bvh = BVHTree.FromPolygons(hverts, hpolys)
    he.to_mesh_clear()

    mw_p = phone.matrix_world
    mw_p_inv = mw_p.inverted()
    rot_p = mw_p.to_3x3()
    phone.data.calc_normals_split() if hasattr(phone.data, "calc_normals_split") else None

    n_dented = 0
    max_dent = 0.0
    for v in phone.data.vertices:
        wco = mw_p @ v.co
        hit = hand_bvh.find_nearest(wco)
        if hit[0] is None:
            continue
        loc, _nor, _idx, dist = hit
        if dist is None or dist > contact_range:
            continue
        wn = (rot_p @ v.normal).normalized()
        # 손이 폰 바깥쪽(법선 방향)에 있어야 누르는 것 → 안쪽으로 함몰
        if (loc - wco).dot(wn) <= 0:
            continue
        amt = press_depth * (1.0 - dist / contact_range)   # 가까울수록 깊게
        new_wco = wco - wn * amt
        v.co = mw_p_inv @ new_wco
        n_dented += 1
        max_dent = max(max_dent, amt)

    phone.data.update()
    return {"dented_verts": n_dented, "max_dent": round(max_dent, 4)}


def main():
    # 인자: -- <cmd.json> <result.json>
    argv = sys.argv
    if "--" in argv:
        argv = argv[argv.index("--") + 1:]
    cmd_path, result_path = argv[0], argv[1]

    with open(cmd_path) as f:
        cmd = json.load(f)

    try:
        result = _run(cmd)
    except Exception as e:
        import traceback
        result = {"ok": False, "error": str(e), "trace": traceback.format_exc()}

    with open(result_path, "w") as f:
        json.dump(result, f)


if __name__ == "__main__":
    main()
