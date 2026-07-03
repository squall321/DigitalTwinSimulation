# headless Blender 진입점: cmd.json을 받아 명령을 실행하고 result.json으로 결과 회수.
# MCP/app(py3.10)과 Blender(py3.11)의 프로세스 경계 — 주고받는 데이터는 순수 JSON dict만.
import bpy
import sys
import json
import os
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

    # 3) 위치맞춤(승자 접근 A): 손바닥 윗면을 폰 뒷면에 붙이고, 손가락 뿌리가
    #    폰 가까운 긴모서리를 넘어 앞면으로 말리게 한다.
    #    손 local: 손바닥 두께 t=25 → 반두께 12.5, 손가락 뿌리 y≈90.
    #    손은 armature의 자식 → armature만 이동(이중변환 방지).
    pbb = [phone.matrix_world @ Vector(c) for c in phone.bound_box]
    pmin = Vector((min(v.x for v in pbb), min(v.y for v in pbb), min(v.z for v in pbb)))
    pmax = Vector((max(v.x for v in pbb), max(v.y for v in pbb), max(v.z for v in pbb)))
    center = (pmin + pmax) * 0.5
    half_t = 25.0 * 0.5            # PALM 두께 반(손바닥 윗면이 z=+half_t local)
    arm.location = (
        center.x,                 # x: 폰 중심
        pmax.y - 90.0,            # y: 손가락 뿌리(y≈90)가 가까운 긴모서리(pmax.y)에
        pmin.z - half_t,          # z: 손바닥 윗면이 폰 뒷면(pmin.z)에 닿게
    )
    arm.rotation_euler = (0, 0, 0)
    bpy.context.view_layer.update()

    # 4) 그립 프리셋 적용
    grip_meta = grip_ops.apply_grip(hand_info, style=style)

    # 5) shrinkwrap 2패스(관통 완화 + 밀착, 승자 graft)
    grip_ops.shrinkwrap_fingers_to_phone(hand.name, phone.name)
    bpy.context.view_layer.update()

    # 6) 관통 측정
    pen = grip_ops.measure_penetration(hand.name, phone.name)

    # 7) 출력: 손 포즈 STL + 폰 외곽(그립으로 함몰된 버전 = 현재는 원본 외곽 복제,
    #    실제 함몰은 슬라이스4 모핑이 손가락 접촉면을 반영. 여기선 접촉 메타만 전달)
    result = {
        "hand": hand_info, "style": style, "penetration": pen, "grip_meta": grip_meta,
        "phone_bbox": {"min": list(pmin), "max": list(pmax)},
    }
    if hand_out:
        _export_object_stl(hand.name, hand_out)
        result["hand_stl"] = hand_out
    if edited_out:
        _export_object_stl(phone.name, edited_out)
        result["edited_outer_stl"] = edited_out
    return {"ok": True, "result": result}


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
