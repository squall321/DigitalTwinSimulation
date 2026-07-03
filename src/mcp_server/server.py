# LLM이 자연어로 지시하는 MCP 서버. 7개 고수준 도구로 슬라이스1~4를 노출(DESIGN §5).
# 도구는 flat 인자(중첩 스키마가 LLM 호출과 모순). enum으로 입력 강제. 코어는 mcp를 모른다.
import os
from enum import Enum

from mcp.server.fastmcp import FastMCP

from app.session import GripState
from app import pipeline

# 세션 작업 디렉토리 베이스(환경변수로 덮어쓰기 가능).
_BASE = os.environ.get("DTS_SESSION_DIR", "/tmp/dts_sessions")

mcp = FastMCP("digital-twin-simulation")


class GripStyle(str, Enum):
    natural = "natural"
    tight = "tight"
    pinch = "pinch"
    edge_hold = "edge_hold"
    loose = "loose"


class Handedness(str, Enum):
    left = "left"
    right = "right"


class MorphMethod(str, Enum):
    laplacian = "laplacian"
    rbf = "rbf"


def _result_dict(state: GripState, res) -> dict:
    """StageResult를 MCP 응답 dict로. 코어 dataclass를 경계에서만 직렬화."""
    out = {
        "ok": res.ok,
        "session_id": state.session_id,
        "phone_stage": state.phone_stage.value,
        "hand_stage": state.hand_stage.value,
        "message": res.message,
        "artifacts": {**state.artifacts},
        "metrics": res.diagnostics,
    }
    if not res.ok and "suggested_scale" in res.diagnostics:
        out["hint"] = res.message
    return out


def _session(session_id: str) -> GripState:
    sid = session_id or "default"
    return GripState.load_or_create(sid, _BASE)


@mcp.tool()
def extract_surface(k_file: str, session_id: str = "default",
                    parts: list[int] | None = None,
                    merge_shells: bool = True) -> dict:
    """LS-DYNA .k 파일에서 폰 외곽 표면 STL을 추출하고 원본 메쉬를 보존한다.
    파이프라인의 시작점. 폰을 불러올 때 가장 먼저 호출한다."""
    state = _session(session_id)
    res = pipeline.extract_surface(state, k_file, parts=parts, merge_shells=merge_shells)
    return _result_dict(state, res)


@mcp.tool()
def inspect_k(k_file: str) -> dict:
    """.k 파일의 PART 목록과 요소 타입을 조사한다. extract가 실패하거나
    어떤 PART를 포함할지 모를 때 먼저 호출해 실제 구조를 본다."""
    res = pipeline.inspect_k(k_file)
    return {"ok": res.ok, "message": res.message, "parts": res.diagnostics.get("parts", {}),
            "n_nodes": res.diagnostics.get("n_nodes")}


@mcp.tool()
def load_hand(session_id: str = "default",
              handedness: Handedness = Handedness.right) -> dict:
    """절차적 리깅 손을 생성한다. extract_surface 다음에 호출한다."""
    state = _session(session_id)
    res = pipeline.load_hand(state, handedness=handedness.value)
    return _result_dict(state, res)


@mcp.tool()
def grip_phone(session_id: str = "default",
               style: GripStyle = GripStyle.natural) -> dict:
    """손이 폰을 자연스럽게 쥐게 한다. load_hand 다음에 호출한다.
    그립 접촉으로 폰 외곽이 함몰된 phone_edited_outer.stl을 만든다(모핑 입력)."""
    state = _session(session_id)
    res = pipeline.grip_phone(state, style=style.value)
    return _result_dict(state, res)


class EditOp(str, Enum):
    scale_thickness = "scale_thickness"
    round_corners = "round_corners"
    dent = "dent"


@mcp.tool()
def edit_formfactor(session_id: str = "default",
                    op: EditOp = EditOp.scale_thickness,
                    factor: float = 1.0,
                    radius: float = 5.0,
                    depth: float = 1.0,
                    center_x: float = 0.0,
                    center_y: float = 0.0) -> dict:
    """폰 폼팩터를 파라메트릭 편집해 모핑 입력을 만든다. 그립 대신 직접 형상 변경.
    op=scale_thickness는 factor(두께 배율), round_corners는 radius(모서리 R),
    dent는 center_x/center_y/radius/depth(국소 함몰). extract_surface 다음에 호출."""
    state = _session(session_id)
    kw = {"scale_thickness": {"factor": factor},
          "round_corners": {"radius": radius},
          "dent": {"center": (center_x, center_y), "radius": radius, "depth": depth}}[op.value]
    res = pipeline.edit_formfactor(state, op.value, **kw)
    return _result_dict(state, res)


@mcp.tool()
def morph_phone(session_id: str = "default",
                method: MorphMethod = MorphMethod.laplacian,
                scale: float = 1.0) -> dict:
    """그립으로 편집된 폰 외곽을 체적 메쉬에 전파해 재해석 가능한 메쉬를 만든다.
    요소가 뒤집히면(과한 변형) 실패하며 scale을 줄이라는 hint를 준다."""
    state = _session(session_id)
    res = pipeline.morph_phone(state, method=method.value, scale=scale)
    return _result_dict(state, res)


@mcp.tool()
def export_solid_k(session_id: str = "default", out_path: str = "") -> dict:
    """모핑된 솔리드 .k 파일을 지정 경로로 내보낸다. morph_phone 다음에 호출한다."""
    state = _session(session_id)
    res = pipeline.export_solid_k(state, out_path=out_path or None)
    return _result_dict(state, res)


def main():
    mcp.run()


if __name__ == "__main__":
    main()
