# 11번: 소켓 백엔드 Adapter + JSONL 프로토콜 검증. bpy 실행은 GUI 필요라 프로토콜만 검증.
import json
import socket
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from app.blender_io import run_socket, run_headless, get_backend  # noqa: E402


def test_adapter_selects_backend():
    """get_backend가 mode에 맞는 백엔드를 반환(Adapter 선택 지점)."""
    assert get_backend("socket") is run_socket
    assert get_backend("headless") is run_headless
    assert get_backend() is run_headless           # 기본 headless


def test_socket_jsonl_roundtrip():
    """run_socket이 JSONL 프레이밍으로 명령 전송 → 응답 파싱(bpy 무관)."""
    port = 47812
    ready = threading.Event()

    def mock_server():
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(("127.0.0.1", port))
        s.listen(1)
        ready.set()
        conn, _ = s.accept()
        buf = b""
        while b"\n" not in buf:
            buf += conn.recv(4096)
        line, _ = buf.split(b"\n", 1)
        cmd = json.loads(line.decode())
        resp = {"ok": True, "result": {"echo": cmd["op"]}}
        conn.sendall((json.dumps(resp) + "\n").encode())
        conn.close()
        s.close()

    th = threading.Thread(target=mock_server, daemon=True)
    th.start()
    assert ready.wait(2)

    r = run_socket({"op": "grip_phone", "params": {"style": "tight"}},
                   port=port, timeout=5)
    assert r["ok"]
    assert r["result"]["echo"] == "grip_phone"


def test_socket_addon_importable():
    """소켓 애드온이 bl_info와 핵심 함수를 갖는지(구조 검증)."""
    src = (Path(__file__).resolve().parents[1] / "src" / "blender_core"
           / "socket_addon.py").read_text()
    assert "bl_info" in src
    assert "def start_server" in src and "def stop_server" in src
    assert "bpy.app.timers" in src         # 메인스레드 디퍼(스레드 안전)
    assert "def register" in src           # Blender 애드온 훅
