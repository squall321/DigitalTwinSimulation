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
