# 9번: 실제 MCP stdio 프로토콜로 클라이언트↔서버 도구 호출 검증.
import json
import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "tests" / "fixtures"))

pytest.importorskip("mcp")
from mcp import ClientSession, StdioServerParameters  # noqa: E402
from mcp.client.stdio import stdio_client  # noqa: E402
from make_phone_k import make_phone_k  # noqa: E402

VENV_PY = ROOT / ".venv" / "bin" / "python"
_HAS_VENV = VENV_PY.exists()
venv_required = pytest.mark.skipif(not _HAS_VENV, reason="로컬 venv python 없음")


def _params(session_dir):
    return StdioServerParameters(
        command=str(VENV_PY),
        args=["-m", "mcp_server.server"],
        env={"PYTHONPATH": str(ROOT / "src"), "DTS_SESSION_DIR": str(session_dir)},
    )


@venv_required
@pytest.mark.anyio
async def test_mcp_tools_callable_via_stdio(tmp_path):
    """실제 MCP stdio 세션에서 도구 목록 + extract_surface/inspect_k 호출."""
    make_phone_k(str(tmp_path / "phone.k"))
    async with stdio_client(_params(tmp_path / "sess")) as (read, write):
        async with ClientSession(read, write) as s:
            await s.initialize()

            tools = await s.list_tools()
            names = {t.name for t in tools.tools}
            assert {"extract_surface", "inspect_k", "load_hand", "grip_phone",
                    "morph_phone", "export_solid_k", "edit_formfactor"} <= names

            r = await s.call_tool("extract_surface",
                                  {"k_file": str(tmp_path / "phone.k"), "session_id": "t"})
            d = json.loads(r.content[0].text)
            assert d["ok"] and d["phone_stage"] == "extracted"
            assert d["metrics"]["n_tris"] == 1040

            r = await s.call_tool("inspect_k", {"k_file": str(tmp_path / "phone.k")})
            d = json.loads(r.content[0].text)
            assert d["ok"] and d["n_nodes"] == 693


@pytest.fixture
def anyio_backend():
    return "asyncio"
