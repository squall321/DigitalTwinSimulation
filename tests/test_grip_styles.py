# 그립 스타일 프리셋 검증. 5개 스타일이 모두 정의되고 서로 다른 각도를 갖는지.
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_all_styles_defined():
    """GRIP_PRESETS에 5개 스타일이 완전한 스키마로 정의됨."""
    # bpy 없이 프리셋 딕셔너리만 import (grip_ops는 bpy 의존이라 소스 파싱).
    src = (Path(__file__).resolve().parents[1] / "src" / "blender_core" / "grip_ops.py").read_text()
    ns = {}
    # GRIP_PRESETS 리터럴만 안전 추출
    start = src.index("GRIP_PRESETS = {")
    depth = 0
    end = start
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    exec(src[start:end], ns)
    presets = ns["GRIP_PRESETS"]

    expected = {"natural", "tight", "pinch", "edge_hold", "loose"}
    assert set(presets.keys()) == expected

    for name, p in presets.items():
        assert set(p["per_finger"].keys()) == {"index", "middle", "ring", "pinky"}
        assert all(len(v) == 3 for v in p["per_finger"].values())   # 3관절
        assert len(p["thumb"]) == 3
        assert set(p["spread"].keys()) == {"index", "middle", "ring", "pinky"}


def test_styles_are_distinct():
    """pinch는 검지만 굽고 나머지 손가락은 펴진다(natural과 구분)."""
    src = (Path(__file__).resolve().parents[1] / "src" / "blender_core" / "grip_ops.py").read_text()
    ns = {}
    start = src.index("GRIP_PRESETS = {")
    depth = 0
    for i in range(src.index("{", start), len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    exec(src[start:end], ns)
    p = ns["GRIP_PRESETS"]

    # pinch: 중지 근위 굴곡이 검지보다 훨씬 작음(나머지 펴짐)
    assert p["pinch"]["per_finger"]["middle"][0] < p["pinch"]["per_finger"]["index"][0] * 0.5
    # natural: 얇은 폰을 얹어 쥐는 컵 형태 — 주먹처럼 꽉(>1.0)이 아니라 부드럽게 굽음
    n = p["natural"]["per_finger"]
    assert 0.2 < n["middle"][0] < 1.0 and 0.2 < n["pinky"][0] < 1.0
    # 손가락들이 비슷하게 굽음(부채꼴 컵)
    assert abs(n["index"][0] - n["ring"][0]) < 0.2
    # tight는 natural보다 더 굽고, edge_hold/loose는 더 얕다
    assert p["tight"]["per_finger"]["index"][0] > p["natural"]["per_finger"]["index"][0]
    assert p["edge_hold"]["per_finger"]["index"][0] < p["natural"]["per_finger"]["index"][0]


def test_mcp_gripstyle_enum_has_all():
    """MCP GripStyle enum이 5개 스타일을 모두 노출."""
    src = (Path(__file__).resolve().parents[1] / "src" / "mcp_server" / "server.py").read_text()
    for s in ("natural", "tight", "pinch", "edge_hold", "loose"):
        assert f'{s} = "{s}"' in src
