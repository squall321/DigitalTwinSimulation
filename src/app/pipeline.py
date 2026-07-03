# 슬라이스 1~4를 묶는 고수준 파이프라인 함수. MCP/CLI가 공통 호출. mcp를 import하지 않는다.
from pathlib import Path

from core.result import StageResult
from dyna_io.parser import parse_k_file
from dyna_io.surface import build_surface
from dyna_io.stl import write_stl, watertight_diag
from dyna_io.rewrite import rewrite_k
from morph.driver import morph_phone_volume
from app.blender_io import run_headless
from app.session import GripState, PhoneStage, HandStage


def extract_surface(state: GripState, k_file: str, parts=None,
                    merge_shells=True) -> StageResult:
    """폰 .k → 외곽 STL + 원본 보존(슬라이스1)."""
    mesh = parse_k_file(k_file)
    tris, used, diag = build_surface(mesh, parts=parts, merge_shells=merge_shells)
    # tris는 build_surface의 used 인덱싱을 가리킨다 → verts도 반드시 used 순서로.
    # (dense_index의 row2nid는 순서가 달라 인덱스가 어긋나 sliver 삼각형이 생긴다.)
    verts = [tuple(mesh.nodes[nid]) for nid in used]

    out_stl = str(Path(state.workdir) / "phone_outer.stl")
    write_stl(out_stl, verts, tris, binary=True)
    wt = watertight_diag(tris)

    state.src_k = k_file
    state.artifacts["phone_outer"] = out_stl
    state.artifacts["phone_orig_k"] = k_file
    state.phone_stage = PhoneStage.EXTRACTED
    # 폰을 다시 추출하면 하위 산출물(morphed) 무효화(DESIGN §6 단계 후퇴).
    state.artifacts.pop("phone_morphed_k", None)
    state.save()
    return StageResult.success(
        message=f"외곽 추출 완료({len(tris)}삼각형, watertight={wt['watertight']}).",
        artifacts={"phone_outer": out_stl},
        diagnostics={"n_tris": len(tris), "watertight": wt["watertight"]},
    )


def inspect_k(k_file: str) -> StageResult:
    """PART 목록·요소타입 관찰(LLM 자가수정용, DESIGN §5)."""
    mesh = parse_k_file(k_file)
    parts = {}
    for el in mesh.solids:
        parts.setdefault(el.pid, {"type": {}, "count": 0})
        t = el.etype.name
        parts[el.pid]["type"][t] = parts[el.pid]["type"].get(t, 0) + 1
        parts[el.pid]["count"] += 1
    for el in mesh.shells:
        parts.setdefault(el.pid, {"type": {}, "count": 0})
        t = el.etype.name
        parts[el.pid]["type"][t] = parts[el.pid]["type"].get(t, 0) + 1
        parts[el.pid]["count"] += 1
    return StageResult.success(
        message=f"{len(parts)}개 PART, 노드 {len(mesh.nodes)}개.",
        diagnostics={"parts": parts, "n_nodes": len(mesh.nodes)},
    )


def load_hand(state: GripState, handedness="right") -> StageResult:
    """절차적 손 생성(슬라이스2). 폰이 추출된 뒤 호출."""
    if state.phone_stage == PhoneStage.EMPTY:
        return StageResult.fail("먼저 extract_surface로 폰을 불러오세요.")
    hand_stl = str(Path(state.workdir) / "hand.stl")
    res = run_headless({"op": "build_hand", "params": {
        "handedness": handedness, "unit_scale": 1000.0, "export_stl": hand_stl}},
        workdir=state.workdir)
    if not res.get("ok"):
        return StageResult.fail(f"손 생성 실패: {res.get('error')}")
    state.handedness = handedness
    state.hand_stage = HandStage.LOADED
    state.artifacts["hand"] = hand_stl
    state.save()
    return StageResult.success(message="손 로드 완료.", artifacts={"hand": hand_stl})


def grip_phone(state: GripState, style="natural") -> StageResult:
    """손이 폰을 쥐는 그립(슬라이스3). phone_edited_outer.stl 산출(모핑 입력)."""
    if state.hand_stage == HandStage.NONE:
        return StageResult.fail("먼저 load_hand로 손을 불러오세요.")
    phone_outer = state.artifacts.get("phone_outer")
    hand_stl = str(Path(state.workdir) / "grip_hand.stl")
    edited = str(Path(state.workdir) / "phone_edited_outer.stl")
    res = run_headless({"op": "grip_phone", "params": {
        "phone_stl": phone_outer, "style": style, "handedness": state.handedness,
        "hand_stl": hand_stl, "edited_outer_stl": edited}}, workdir=state.workdir)
    if not res.get("ok"):
        return StageResult.fail(f"그립 실패: {res.get('error')}")
    state.grip_style = style
    state.hand_stage = HandStage.GRIPPED
    state.artifacts["grip_hand"] = hand_stl
    state.artifacts["phone_edited_outer"] = edited
    state.save()
    pen = res["result"].get("penetration", {})
    return StageResult.success(
        message=f"그립 완료(style={style}).",
        artifacts={"grip_hand": hand_stl, "phone_edited_outer": edited},
        diagnostics={"penetration": pen},
    )


def morph_phone(state: GripState, method="laplacian", scale=1.0,
                edited_outer=None) -> StageResult:
    """편집 외곽을 체적 메쉬에 전파(슬라이스4). 성공 시 phone_morphed.k."""
    if state.phone_stage == PhoneStage.EMPTY:
        return StageResult.fail("먼저 extract_surface로 폰을 불러오세요.")
    edited = edited_outer or state.artifacts.get("phone_edited_outer")
    if not edited or not Path(edited).exists():
        return StageResult.fail("편집 외곽 STL이 없습니다. grip_phone을 먼저 하거나 edited_outer를 지정하세요.")

    mesh = parse_k_file(state.src_k)
    res = morph_phone_volume(mesh, edited, method=method, scale=scale)
    if not res.ok:
        return res   # 거부 + hint 그대로 전달

    out_k = str(Path(state.workdir) / "phone_morphed.k")
    rw = rewrite_k(mesh, res.artifacts["new_coords"], out_k)
    state.phone_stage = PhoneStage.MORPHED
    state.artifacts["phone_morphed_k"] = out_k
    state.save()
    diag = dict(res.diagnostics)
    diag.update(rw)
    return StageResult.success(
        message=res.message + f" → {out_k}",
        artifacts={"phone_morphed_k": out_k},
        diagnostics=diag,
    )


def edit_formfactor(state: GripState, op: str, **params) -> StageResult:
    """폰 외곽을 파라메트릭 편집해 모핑 입력(phone_edited_outer)을 만든다.

    op: "scale_thickness"(factor), "round_corners"(radius), "dent"(center,radius,depth).
    그립 대신(또는 그립과 별개로) 사용자가 폼팩터를 직접 바꾸는 경로.
    """
    from morph import edit

    src = state.artifacts.get("phone_outer")
    if not src:
        return StageResult.fail("먼저 extract_surface로 폰 외곽을 만드세요.")
    out = str(Path(state.workdir) / "phone_edited_outer.stl")
    fn = {"scale_thickness": edit.scale_thickness,
          "round_corners": edit.round_corners,
          "dent": edit.dent}.get(op)
    if fn is None:
        return StageResult.fail(f"알 수 없는 편집: {op}. "
                                "scale_thickness/round_corners/dent 중 하나.")
    meta = fn(src, out, **params)
    state.artifacts["phone_edited_outer"] = out
    state.save()
    return StageResult.success(message=f"폼팩터 편집 완료({op}).",
                               artifacts={"phone_edited_outer": out},
                               diagnostics=meta)


def export_solid_k(state: GripState, out_path=None) -> StageResult:
    """모핑된 .k를 지정 경로로 내보냄(슬라이스4 산출)."""
    src = state.artifacts.get("phone_morphed_k")
    if not src:
        return StageResult.fail("모핑된 .k가 없습니다. morph_phone을 먼저 하세요.")
    if out_path:
        import shutil
        shutil.copy(src, out_path)
        return StageResult.success(message=f"내보냄: {out_path}",
                                   artifacts={"solid_k": out_path})
    return StageResult.success(message=f"모핑 .k: {src}", artifacts={"solid_k": src})
