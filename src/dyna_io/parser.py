# LS-DYNA .k 파일을 라인 상태머신으로 파싱해 MeshData 생성. 고정폭 우선·공백분할 폴백.
from dyna_io.classify import classify_solid
from dyna_io.model import ElementType, MeshData, ShellElement, SolidElement


def _ints(line: str, width: int, count: int) -> list:
    """고정폭 정수 필드 추출. 빈 슬롯/짧은 라인은 0. 폭 파싱 실패 시 공백분할 폴백."""
    fields = []
    for i in range(count):
        chunk = line[i * width:(i + 1) * width]
        if not chunk.strip():
            fields.append(0)
            continue
        try:
            fields.append(int(chunk))
        except ValueError:
            return _ints_freeform(line, count)
    return fields


def _ints_freeform(line: str, count: int) -> list:
    """공백분할 폴백. 콤마(자유형식)는 현 샘플에 없음 → 만나면 명시적 에러."""
    if "," in line:
        raise ValueError(f"comma free-format .k not supported: {line!r}")
    toks = line.split()
    vals = [int(t) for t in toks[:count]]
    vals += [0] * (count - len(vals))
    return vals


def _node_line(line: str):
    """*NODE 한 줄 파싱 → (nid, (x,y,z), (tc,rc)). 고정폭 8/16/16/16/8/8, 폴백 공백분할."""
    if "," in line:
        raise ValueError(f"comma free-format *NODE not supported: {line!r}")
    try:
        nid = int(line[0:8])
        x = float(line[8:24])
        y = float(line[24:40])
        z = float(line[40:56])
        tc_s, rc_s = line[56:64].strip(), line[64:72].strip()
        tc = int(tc_s) if tc_s else 0
        rc = int(rc_s) if rc_s else 0
        return nid, (x, y, z), (tc, rc)
    except ValueError:
        toks = line.split()
        if len(toks) < 4:
            raise ValueError(f"malformed *NODE line: {line!r}")
        nid = int(toks[0])
        x, y, z = float(toks[1]), float(toks[2]), float(toks[3])
        tc = int(toks[4]) if len(toks) > 4 else 0
        rc = int(toks[5]) if len(toks) > 5 else 0
        return nid, (x, y, z), (tc, rc)


def parse_k_file(path: str) -> MeshData:
    """라인 상태머신으로 .k 파싱. $ 주석/빈줄 스킵, *키워드로 모드 전환."""
    mesh = MeshData(src_path=path)
    mode = None          # None | "NODE" | "SOLID" | "SHELL" | "PART"
    part_pending = None  # *PART 직후 title/data 라인 카운터

    with open(path, "r") as f:
        for raw in f:
            line = raw.rstrip("\n")
            stripped = line.strip()

            if stripped.startswith("$") or stripped == "":
                continue

            if stripped.startswith("*"):
                kw = stripped.upper()
                if kw.startswith("*NODE") and not kw.startswith("*NODE_"):
                    mode = "NODE"
                elif kw.startswith("*ELEMENT_SOLID"):
                    mode = "SOLID"
                elif kw.startswith("*ELEMENT_SHELL"):
                    mode = "SHELL"
                elif kw.startswith("*PART"):
                    mode = "PART"
                    part_pending = {"line": 0, "name": ""}
                else:
                    mode = None  # 그 외 키워드 블록은 무시
                continue

            if mode == "NODE":
                nid, xyz, (tc, rc) = _node_line(line)
                mesh.nodes[nid] = xyz
                if tc or rc:
                    mesh.node_constraints[nid] = (tc, rc)

            elif mode == "SOLID":
                f10 = _ints(line, 8, 10)
                eid, pid = f10[0], f10[1]
                n8 = f10[2:10]
                mesh.solids.append(SolidElement(eid, pid, n8, classify_solid(n8)))

            elif mode == "SHELL":
                f6 = _ints(line, 8, 6)
                eid, pid = f6[0], f6[1]
                n = f6[2:6]
                uniq = list(dict.fromkeys(n))
                etype = ElementType.TRI3 if len(uniq) == 3 else ElementType.QUAD4
                mesh.shells.append(ShellElement(eid, pid, n, etype))

            elif mode == "PART":
                # *PART 다음: title 라인 1개, 그 다음 데이터 라인(PID SECID MID ...).
                if part_pending["line"] == 0:
                    part_pending["name"] = line.strip()
                    part_pending["line"] = 1
                else:
                    f8 = _ints(line, 10, 8)
                    pid = f8[0]
                    mesh.parts[pid] = {
                        "name": part_pending["name"],
                        "secid": f8[1],
                        "mid": f8[2],
                    }
                    mode = None
                    part_pending = None

    return mesh
