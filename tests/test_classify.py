# 8슬롯 노드 반복 패턴으로 솔리드 타입을 판정하는 classify_solid 단언.
from dyna_io.classify import classify_solid
from dyna_io.model import ElementType


def test_hex8_distinct_eight():
    assert classify_solid([1, 2, 3, 4, 5, 6, 7, 8]) == ElementType.HEX8


def test_tet4_degenerate_last_repeat():
    # 실측 ex02 PID2: 고유 4노드, 마지막 노드 반복 저장.
    assert classify_solid([1001, 1002, 1012, 1122, 1122, 1122, 1122, 1122]) == ElementType.TET4


def test_tet4_synthetic():
    assert classify_solid([1, 2, 3, 4, 4, 4, 4, 4]) == ElementType.TET4


def test_pyramid5_five_unique():
    assert classify_solid([1, 2, 3, 4, 5, 5, 5, 5]) == ElementType.PYRAMID5


def test_wedge6_six_unique():
    assert classify_solid([1, 2, 3, 4, 5, 6, 6, 6]) == ElementType.WEDGE6


def test_invalid_seven_unique():
    assert classify_solid([1, 2, 3, 4, 5, 6, 7, 5]) == ElementType.INVALID


def test_order_preserving_count():
    # 중복이 마지막이 아니라 중간에 있어도 고유 노드 수로 판정.
    assert classify_solid([1, 2, 2, 3, 4, 4, 4, 4]) == ElementType.TET4
