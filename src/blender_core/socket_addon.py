# GUI Blender 상주 소켓 서버 애드온. headless와 동일한 _run(cmd) 디스패치를 재사용.
# JSONL 프레이밍(개행 구분)으로 명령 수신 → 결과 반환. 실시간 조정용(Adapter 두번째 백엔드).
#
# 중요(스레드 안전): bpy 연산은 메인스레드에서만 안전하다. 소켓 수신은 워커 스레드가
# 하되, 실제 _run(bpy 연산)은 bpy.app.timers로 메인스레드에 디퍼한다(GUI 이벤트 루프
# 필요). headless --background에선 타이머 루프가 없어 이 애드온은 GUI Blender 전용이다.
import json
import queue
import socket
import threading

bl_info = {
    "name": "DigitalTwin Socket Server",
    "blender": (4, 5, 0),
    "category": "Development",
}

_HOST = "127.0.0.1"
_PORT = 47800
_server = {"sock": None, "thread": None, "running": False}
# 워커 스레드 → 메인스레드 작업 큐. 각 항목: (cmd, reply_event, result_box).
_work_q = queue.Queue()


def _dispatch_main_thread(cmd: dict) -> dict:
    """메인스레드에서 실행. bpy 연산 안전. headless runner와 동일 디스패치 재사용."""
    try:
        from blender_core.runner import _run
        return _run(cmd)
    except Exception as e:
        import traceback
        return {"ok": False, "error": str(e), "trace": traceback.format_exc()}


def _timer_pump():
    """bpy.app.timers 콜백(메인스레드). 큐의 명령을 처리하고 응답을 채운다."""
    try:
        while True:
            cmd, ev, box = _work_q.get_nowait()
            box["result"] = _dispatch_main_thread(cmd)
            ev.set()
    except queue.Empty:
        pass
    return 0.05 if _server["running"] else None       # None이면 타이머 해제


def _serve():
    """소켓 워커 스레드. 명령을 받아 메인스레드 큐에 넣고 응답을 기다린다."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((_HOST, _PORT))
    s.listen(1)
    s.settimeout(0.5)
    _server["sock"] = s
    while _server["running"]:
        try:
            conn, _ = s.accept()
        except socket.timeout:
            continue
        with conn:
            buf = b""
            while _server["running"]:
                data = conn.recv(4096)
                if not data:
                    break
                buf += data
                while b"\n" in buf:
                    line, buf = buf.split(b"\n", 1)
                    if not line.strip():
                        continue
                    cmd = json.loads(line.decode())
                    ev = threading.Event()
                    box = {}
                    _work_q.put((cmd, ev, box))       # 메인스레드가 처리
                    ev.wait(timeout=180)
                    result = box.get("result", {"ok": False, "error": "timeout"})
                    conn.sendall((json.dumps(result) + "\n").encode())
    s.close()


def start_server():
    if _server["running"]:
        return
    _server["running"] = True
    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    _server["thread"] = t
    # 메인스레드 펌프 등록(GUI 이벤트 루프에서 주기 호출).
    import bpy
    if not bpy.app.timers.is_registered(_timer_pump):
        bpy.app.timers.register(_timer_pump)


def stop_server():
    _server["running"] = False


# Blender 애드온 등록 훅(GUI에서 활성화 시).
def register():
    start_server()


def unregister():
    stop_server()


if __name__ == "__main__":
    # headless에서 서버만 띄워 프로토콜 검증하는 용도.
    import time
    start_server()
    while True:
        time.sleep(1)
