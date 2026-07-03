# headless Blender를 subprocess로 실행하는 어댑터. py3.10(여기) ↔ py3.11(Blender) JSON 경계.
import json
import os
import subprocess
import tempfile
from pathlib import Path

# 프로젝트 루트와 Blender 바이너리.
_ROOT = Path(__file__).resolve().parents[2]
_SRC = _ROOT / "src"
_RUNNER = _SRC / "blender_core" / "runner.py"


def _blender_bin() -> str:
    return os.environ.get("DTS_BLENDER_BIN", "/snap/bin/blender")


def run_headless(cmd: dict, workdir: str = None, timeout: int = 180) -> dict:
    """cmd dict를 headless Blender에서 실행하고 result dict를 회수한다.

    결과는 stdout이 아니라 result.json 파일로만 회수한다(애드온 로그가 stdout 오염).
    cmd/result는 순수 JSON dict — dataclass를 프로세스 경계로 넘기지 않는다.
    """
    wd = Path(workdir) if workdir else Path(tempfile.mkdtemp(prefix="dts_blender_"))
    wd.mkdir(parents=True, exist_ok=True)
    cmd_path = wd / "cmd.json"
    result_path = wd / "result.json"
    cmd_path.write_text(json.dumps(cmd))
    if result_path.exists():
        result_path.unlink()

    proc = subprocess.run(
        [
            _blender_bin(), "--background", "--factory-startup",
            "--python", str(_RUNNER),
            "--", str(cmd_path), str(result_path),
        ],
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        capture_output=True, text=True, timeout=timeout,
    )

    if not result_path.exists():
        raise RuntimeError(
            f"Blender가 result.json을 남기지 않음 (op={cmd.get('op')}).\n"
            f"stderr 마지막:\n{proc.stderr[-2000:]}"
        )
    return json.loads(result_path.read_text())


# --- Adapter 두 번째 백엔드: 상주 GUI Blender 소켓 채널 ---
# run_headless와 동일한 (cmd dict) -> (result dict) 계약. 실시간 조정용.
_SOCKET_HOST = "127.0.0.1"
_SOCKET_PORT = 47800


def run_socket(cmd: dict, workdir: str = None, timeout: int = 180,
               host: str = _SOCKET_HOST, port: int = _SOCKET_PORT) -> dict:
    """상주 Blender 소켓 서버에 JSONL 명령을 보내고 결과를 받는다.

    run_headless와 시그니처/반환이 동일 → 호출부는 백엔드를 몰라도 된다(Adapter).
    소켓 서버(blender_core/socket_addon.py)가 GUI Blender 안에서 떠 있어야 한다.
    """
    import socket

    with socket.create_connection((host, port), timeout=timeout) as s:
        s.sendall((json.dumps(cmd) + "\n").encode())
        buf = b""
        while b"\n" not in buf:
            data = s.recv(4096)
            if not data:
                break
            buf += data
    line = buf.split(b"\n", 1)[0]
    return json.loads(line.decode())


def get_backend(mode: str = "headless"):
    """실행 모드에 맞는 백엔드 함수를 반환. Adapter 선택 지점(if 한 줄)."""
    return run_socket if mode == "socket" else run_headless
