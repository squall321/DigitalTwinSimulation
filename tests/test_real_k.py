# 실파일(ex01/ex02)을 Track A parse_k_file로 파싱해 PID분류·요소수·외곽추출을 단언.
import os
from collections import Counter

import pytest

from dyna_io.boundary import outer_boundary
from dyna_io.faces import extract_free_faces
from dyna_io.model import ElementType
from dyna_io.parser import parse_k_file
from dyna_io.surface import build_surface

EX01 = "/data/ball_drop_test_v3/ex01_hex8_m027_baseline/ex01_hex8_m027_baseline.k"
EX02 = "/data/ball_drop_test_v3/ex02_tet4_m027_baseline/ex02_tet4_m027_baseline.k"


@pytest.fixture(scope="module")
def ex01():
    if not os.path.exists(EX01):
        pytest.skip("ex01 실파일 없음")
    return parse_k_file(EX01)


@pytest.fixture(scope="module")
def ex02():
    if not os.path.exists(EX02):
        pytest.skip("ex02 실파일 없음")
    return parse_k_file(EX02)


# --- ex01: 순수 HEX8 3-part ---

def test_ex01_node_and_solid_counts(ex01):
    assert len(ex01.nodes) == 1502
    assert len(ex01.solids) == 976
    assert len(ex01.shells) == 0


def test_ex01_all_hex8(ex01):
    assert all(e.etype == ElementType.HEX8 for e in ex01.solids)
    by_pid = Counter(e.pid for e in ex01.solids)
    assert by_pid == {1: 144, 2: 800, 3: 32}


def test_ex01_surface_nonempty(ex01):
    tris, used, diag = build_surface(ex01)
    assert len(tris) > 0
    assert len(used) > 0
    assert diag["n_boundary_faces"] == 780


# --- ex02: HEX8 + degenerate-TET 혼재 ---

def test_ex02_node_and_solid_counts(ex02):
    assert len(ex02.nodes) == 1502
    assert len(ex02.solids) == 4176
    assert len(ex02.shells) == 0


def test_ex02_part_classification(ex02):
    # PID2 = degenerate TET4(4000), PID1·PID3 = HEX8(144/32).
    by_pid_type = Counter((e.pid, e.etype) for e in ex02.solids)
    assert by_pid_type[(1, ElementType.HEX8)] == 144
    assert by_pid_type[(2, ElementType.TET4)] == 4000
    assert by_pid_type[(3, ElementType.HEX8)] == 32
    # PID2에 HEX8이 섞여 들어가지 않았는지(혼재 분류 정확성).
    assert (2, ElementType.HEX8) not in by_pid_type


def test_ex02_degenerate_tet_raw_preserved(ex02):
    # eid 1001은 8슬롯 원형(마지막 노드 반복)을 보존하면서 TET4로 분류.
    el = next(e for e in ex02.solids if e.eid == 1001)
    assert el.etype == ElementType.TET4
    assert len(el.node_ids) == 8
    assert el.node_ids == [1001, 1002, 1012, 1122, 1122, 1122, 1122, 1122]


def test_ex02_tet_block_outer_shell(ex02):
    # tet PID2 단독: 자유면 9600개 중 진짜 외곽 1040개(비conformal 가짜면 제외).
    tets = [e for e in ex02.solids if e.pid == 2]
    free, _ = extract_free_faces(tets, ex02.nodes)
    assert len(free) == 9600
    bnd, nids = outer_boundary(free, ex02.nodes, solids=tets)
    assert len(bnd) == 1040
    assert len(nids) > 0


def test_ex02_full_surface_boundary_nids_nonempty(ex02):
    # 전체 assembly 외곽 추출이 예외 없이 동작하고 boundary_nids 비어있지 않음.
    tris, used, diag = build_surface(ex02)
    assert diag["n_boundary_faces"] == 1200
    assert len(tris) > 0
    assert len(used) > 0  # used == boundary_nids 집합(인덱스 공간)
