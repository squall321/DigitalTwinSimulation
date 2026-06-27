# 손이 쥐기 적당한 스마트폰형 박스(hex8 메쉬) LS-DYNA .k 합성 생성기. 슬라이스3~5 테스트 fixture.
import sys


def make_phone_k(path, w=70.0, h=150.0, t=8.0, nx=10, ny=20, nz=2):
    """폰형 박스를 hex8 정형 메쉬로 .k 생성. 원점 기준 (0,0,0)~(w,h,t)."""
    nodes = {}
    nid = 1
    grid = {}
    for k in range(nz + 1):
        for j in range(ny + 1):
            for i in range(nx + 1):
                x = w * i / nx
                y = h * j / ny
                z = t * k / nz
                nodes[nid] = (x, y, z)
                grid[(i, j, k)] = nid
                nid += 1

    elems = []
    eid = 1
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                n = [
                    grid[(i, j, k)], grid[(i + 1, j, k)],
                    grid[(i + 1, j + 1, k)], grid[(i, j + 1, k)],
                    grid[(i, j, k + 1)], grid[(i + 1, j, k + 1)],
                    grid[(i + 1, j + 1, k + 1)], grid[(i, j + 1, k + 1)],
                ]
                elems.append((eid, 1, n))
                eid += 1

    lines = ["*KEYWORD", "*TITLE", "synthetic_phone_70x150x8mm"]
    lines.append("*PART")
    lines.append("Phone_Body")
    lines.append("         1         1         1         0         0         0         0         0")
    lines.append("*SECTION_SOLID")
    lines.append("         1         1")
    lines.append("*MAT_ELASTIC")
    lines.append("         1   2.7E-9      70000      0.33")
    lines.append("*NODE")
    for i, (x, y, z) in nodes.items():
        lines.append(f"{i:8d}{x:16.6f}{y:16.6f}{z:16.6f}       0       0")
    lines.append("*ELEMENT_SOLID")
    for eid, pid, n in elems:
        lines.append(f"{eid:8d}{pid:8d}" + "".join(f"{x:8d}" for x in n))
    lines.append("*END")

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    return {"nodes": len(nodes), "elements": len(elems), "bbox": [w, h, t]}


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "phone.k"
    info = make_phone_k(out)
    print(f"생성: {out}  nodes={info['nodes']} elems={info['elements']} bbox={info['bbox']}")
