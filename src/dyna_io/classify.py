# 8슬롯 노드 반복 패턴(고유 노드 수, 순서보존)으로 솔리드 요소 타입 판정.
from dyna_io.model import ElementType


def classify_solid(n8: list) -> ElementType:
    """8슬롯 node_ids에서 순서보존 고유 노드 수로 타입 판정.

    degenerate hex는 마지막 노드를 반복 저장한다: TET4=고유4, PYRAMID5=5,
    WEDGE6=6, HEX8=8. 그 외는 INVALID.
    """
    u = list(dict.fromkeys(n8))  # 순서보존 고유 노드
    return {
        4: ElementType.TET4,
        5: ElementType.PYRAMID5,
        6: ElementType.WEDGE6,
        8: ElementType.HEX8,
    }.get(len(u), ElementType.INVALID)
