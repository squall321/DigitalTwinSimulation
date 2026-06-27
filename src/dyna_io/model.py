# .k 파싱 결과 자료구조. 원본 NID/연결성/degenerate 8슬롯 원형을 보존(모핑 입력원).
from dataclasses import dataclass, field
from enum import Enum

import numpy as np


class ElementType(Enum):
    TET4 = 4
    PYRAMID5 = 5
    WEDGE6 = 6
    HEX8 = 8
    TRI3 = 103
    QUAD4 = 104
    INVALID = -1


@dataclass
class SolidElement:
    eid: int
    pid: int
    node_ids: list          # 원형 8슬롯 (degenerate 반복 유지 → .k 복원용)
    etype: ElementType


@dataclass
class ShellElement:
    eid: int
    pid: int
    node_ids: list
    etype: ElementType


@dataclass
class MeshData:
    nodes: dict = field(default_factory=dict)             # NID -> (x, y, z)
    node_constraints: dict = field(default_factory=dict)  # NID -> (tc, rc)
    solids: list = field(default_factory=list)
    shells: list = field(default_factory=list)
    parts: dict = field(default_factory=dict)
    src_path: str = ""

    def dense_index(self):
        """요소가 참조하는 노드만 모아 dense 배열로. 고립 노드는 제외.

        returns (X(N,3) float64, nid2row dict, row2nid list).
        """
        referenced = []
        seen = set()
        for el in self.solids:
            for nid in dict.fromkeys(el.node_ids):  # 순서보존 고유
                if nid not in seen:
                    seen.add(nid)
                    referenced.append(nid)
        for el in self.shells:
            for nid in dict.fromkeys(el.node_ids):
                if nid not in seen:
                    seen.add(nid)
                    referenced.append(nid)
        row2nid = referenced
        nid2row = {nid: i for i, nid in enumerate(row2nid)}
        X = np.array([self.nodes[nid] for nid in row2nid], dtype=np.float64).reshape(-1, 3)
        return X, nid2row, row2nid
