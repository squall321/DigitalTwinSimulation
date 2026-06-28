# *NODE 좌표만 패치하고 나머지 원문 byte를 보존해 .k 재작성. 좌표의존 카드는 경고만.
# 좌표 의존 카드: 모핑이 형상을 바꾸면 물리가 틀어질 수 있어 존재 시 경고(DESIGN §11-1).
_COORD_DEPENDENT_CARDS = (
    "*INITIAL_VELOCITY_GENERATION",
    "*DEFINE_COORDINATE_NODES",
    "*CONSTRAINED_",
    "*BOUNDARY_PRESCRIBED",
)


def _fmt_node_line(nid, xyz, tail):
    """*NODE 라인 재구성: nid(8) + x,y,z(각 16, %16.6f) + tail(tc/rc 원문 보존)."""
    x, y, z = xyz
    return f"{nid:8d}{x:16.6f}{y:16.6f}{z:16.6f}{tail}"


def rewrite_k(mesh, new_coords, out_path):
    """원본 .k를 읽어 *NODE 좌표만 new_coords로 교체, 나머지는 원문 그대로 기록.

    Args:
      mesh: MeshData (src_path로 원본 재읽기).
      new_coords: {nid -> (x,y,z)} 갱신할 좌표. 없는 nid는 원문 유지.
      out_path: 출력 .k 경로.

    Returns:
      diagnostics dict:
        {"nodes_patched": int, "warnings": [str,...],
         "coord_dependent_cards": [card,...]}
    """
    src = mesh.src_path
    if not src:
        raise ValueError("mesh.src_path가 비어 rewrite 불가(재파싱 source-of-truth 없음)")

    with open(src, "r") as f:
        raw_lines = f.readlines()

    out_lines = []
    mode = None
    patched = 0
    coord_cards = []

    for raw in raw_lines:
        line = raw.rstrip("\n")
        stripped = line.strip()

        if stripped.startswith("*"):
            kw = stripped.upper()
            for card in _COORD_DEPENDENT_CARDS:
                if kw.startswith(card) and card not in coord_cards:
                    coord_cards.append(card)
            if kw.startswith("*NODE") and not kw.startswith("*NODE_"):
                mode = "NODE"
            else:
                mode = None
            out_lines.append(raw)
            continue

        if mode == "NODE" and stripped and not stripped.startswith("$"):
            # nid 추출(고정폭 8 우선, 실패 시 공백분할)
            try:
                nid = int(line[0:8])
            except ValueError:
                toks = line.split()
                nid = int(toks[0]) if toks else None
            if nid is not None and nid in new_coords:
                # tail(tc/rc 등) 원문 보존: 56칸 이후를 그대로
                tail = line[56:] if len(line) > 56 else ""
                newline = _fmt_node_line(nid, new_coords[nid], tail)
                out_lines.append(newline + "\n")
                patched += 1
                continue

        out_lines.append(raw)

    with open(out_path, "w") as f:
        f.writelines(out_lines)

    warnings = []
    if coord_cards:
        warnings.append(
            "좌표 의존 카드 존재 → 모핑으로 형상이 바뀌면 물리가 틀어질 수 있음: "
            + ", ".join(coord_cards)
        )

    return {
        "nodes_patched": patched,
        "warnings": warnings,
        "coord_dependent_cards": coord_cards,
    }
