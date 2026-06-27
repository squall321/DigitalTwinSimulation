# DigitalTwinSimulation — 통합 설계서 (DESIGN.md)

> LS-DYNA `.k` → STL 외곽 추출 → MakeHuman 손 그립 포즈 → 폰 외곽 모핑(내부 스무싱) → 재해석 가능한 솔리드 `.k`. LLM이 자연어로 지시하는 MCP 서버로 노출.

이 문서는 5개 설계 연구(아키텍처/MCP/코어모듈)와 그에 대한 6건의 어드버서리얼 검증(과설계·gaps·feasibility)을 **단일 설계**로 통합한 것이다. 검증에서 실측으로 반증된 가정은 폐기했고, 과설계로 지목된 추상화는 제거했으며, 누락된 데이터 흐름은 채웠다.

---

## 0. 통합 원칙 — 무엇이 바뀌었나

검증이 일관되게 가리킨 결론은 하나다. **PLAN.md는 4개 모듈(M1~M4)과 얇은 CLI/GUI 래퍼만 요구하는데, 연구 설계서들이 그 위에 수직 4계층 + 7패턴 + 듀얼 백엔드 ABC + 이중 결과봉투를 미리 쌓았다.** 코드가 0줄인 상태에서 존재하지 않는 코어 시그니처를 못박은 것이 과설계의 근본 원인이다.

이 설계서가 적용한 6가지 교정 (검증 합의).

1. **수직 4계층 + 불변식 메타룰 폐기.** PLAN의 수평 모듈 구조(M1~M4)를 유지한다. "L2는 bpy를 import 안 한다"는 결의문이 아니라 코드 배치로 자연히 성립시킨다.
2. **Blender 백엔드 ABC + SocketBackend를 슬라이스 5로 연기.** 슬라이스 1~4는 전부 headless로 검증된다(PLAN §4). 두 번째 구현(GUI 소켓)이 코드로 실재할 때 인터페이스를 추출한다. 지금은 `run_headless(cmd_dict) -> result_dict` 함수 하나.
3. **패턴 라벨 제거. 살아남는 추상화는 둘.** Strategy(morph: Laplacian↔RBF — 단, 우선순위 재결정), Adapter(슬라이스 5에서). 나머지(Facade/Pipeline/Memento/Result/Command/Factory)는 라벨을 떼고 "그냥 함수/dataclass/JSON 저장"으로 부른다.
4. **결과 봉투 단일화.** 코어는 mcp를 import하지 않는 평범한 dataclass를 반환. MCP 경계에서만 dict로 직렬화. `StageResult`+`ToolResult` 이중 봉투와 변환 레이어를 만들지 않는다.
5. **두 인터프리터 경계를 명문화.** MCP 서버 Python(3.10) ≠ Blender 번들 Python(3.11)이 **실측 확인**됐다. 프로세스 경계를 넘는 데이터는 dataclass 공유 import 금지, 순수 JSON dict만.
6. **모핑·그립의 실현성 결함을 정면 반영.** (a) tet 자유면이 watertight가 아님(실측), (b) 국소 압입 inversion을 RBF 폴백이 못 고침(실측), (c) 자동 그립 IK 수렴은 환상 — blendshape 프리셋 + shrinkwrap 1패스로 범위 축소.

설계 철학(사용자 CLAUDE.md §2): 최소 코드, 추측성 추상화 금지, 모든 패턴은 **두 번째 구현이 코드로 실재할 때** 정당화. "패턴을 위한 패턴"을 피하는 유일한 방법은 미리 짓지 않는 것이다.

---

## 1. 레이어 아키텍처 (수평 모듈, 계층 메타룰 없음)

PLAN의 M1~M4를 그대로 모듈로. "위/아래" 계층 번호와 불변식 결의문은 쓰지 않는다. 대신 **import 방향 규칙 1줄**로 환경 의존을 격리한다.

```
                  DYNA .k (phone)
                       │
         ┌─────────────▼──────────────┐   순수 numpy. bpy 무관.
  [M1]   │ dyna_io  +  surface         │   슬라이스 1.
         │  .k 파싱 → 자유면 추출 →     │──▶ phone_outer.stl
         │  외곽 표면화 → STL          │    + phone_orig.k 경로 보존
         │  + 표면 NID 목록(sidecar)    │    + boundary_nids.json
         └─────────────┬──────────────┘
                       │
  MakeHuman 손 ──┐     ▼
  (CC0 FBX)      │  ┌──────────────────┐   bpy 안에서만 실행.
                 └─▶│ blender_core     │   슬라이스 2~3.
  [M2/M3]           │  손 로드 · 그립    │──▶ hand_posed.stl
                    │  포즈 · 접촉/관통  │    + phone_edited_outer.stl
                    │  · 폰 외곽 편집    │      (그립/사용자 편집 결과)
                    └─────────┬────────┘
                              │ (편집된 폰 외곽 = 모핑 입력원)
                              ▼
                    ┌──────────────────┐   순수 numpy/scipy. bpy 무관.
  phone_orig.k ────▶│ morph            │   슬라이스 4.
  (재파싱)          │  경계변위 = 편집  │──▶ phone_morphed.k
                    │  외곽 - 원본외곽   │    (*NODE 좌표만 패치)
                    │  → 내부 전파 →     │
                    │  품질게이트 → .k   │
                    └─────────┬────────┘
                              │
  [M4/M5]   ┌──────────────────────────────────┐
            │ cli (배치) · gui addon (슬라이스5)  │  얇은 래퍼.
            │ mcp_server (슬라이스를 도구로 감쌈) │  동일 코어 호출.
            └──────────────────────────────────┘
```

**import 방향 규칙 (유일한 메타룰).**
- `dyna_io` / `surface` / `morph` / `core` 는 `bpy` / `socket` / `subprocess` 를 import하지 않는다 → pytest로 직접 검증 가능.
- `blender_core` 만 `bpy` 를 import. headless 진입점(`runner.py`)이 호출.
- `mcp_server` 는 코어를 **호출만** 한다. 코어는 `mcp_server`를 모른다(역의존 금지).

**모핑 입력원 (검증 B1/A1/A2 해소 — 가장 큰 공백이었음).**
PLAN.md §3 다이어그램이 답을 갖고 있었다. M2(Blender)가 `phone_edited_outer.stl`을 산출하고(line 37), 모핑 경계변위 = `편집외곽 - 원본외곽`(line 44)이다. 즉 **모핑의 변형 원천은 손 그립이 아니라 "편집된 폰 외곽"**이다. 편집은 (a) 슬라이스 3에서 손가락 접촉면으로의 shrinkwrap 함몰, 또는 (b) 슬라이스 5 GUI에서 사용자 폼팩터 편집으로 생긴다. 모핑 코어는 `edited_outer_stl` 경로만 입력으로 받고 편집 수단은 묻지 않는다. **손 그립과 폰 모핑은 직렬이 아니라 "편집된 외곽 STL"을 통해서만 연결되는 부분 독립 트랙**이다 — 이걸 §6 상태모델에 명시한다.

---

## 2. 디렉토리 / 모듈 구조

```
DigitalTwinSimulation/
├── pyproject.toml
├── PLAN.md  checklist.md  context-notes.md  DESIGN.md
├── assets/hands/
│   ├── makehuman_right.fbx          # CC0 1회 export 동봉
│   └── LICENSE                       # CC0 명시 + 본 트리 덤프 결과(슬라이스2)
├── src/
│   ├── core/
│   │   └── result.py                 # StageResult — 단일 결과 dataclass (mcp 무관)
│   │
│   ├── dyna_io/                      # [M1] .k 파싱·라이팅 (순수 numpy)        — 슬라이스 1
│   │   ├── model.py                  #   MeshData, SolidElement, ShellElement, ElementType
│   │   ├── parser.py                 #   parse_k_file (라인 상태머신, TC/RC 보존)
│   │   ├── classify.py               #   classify_solid: 고유노드수+반복패턴 (degenerate)
│   │   ├── faces.py                  #   solid_faces 표 + extract_free_faces + 외향정렬
│   │   ├── surface.py                #   build_surface, triangulate, 혼합 병합
│   │   ├── boundary.py               #   외부경계 connected-component 추출 (비conformal 대응)
│   │   ├── stl.py                    #   write_stl(binary/ascii), watertight 진단
│   │   └── rewrite.py                #   rewrite_k: *NODE 좌표만 패치, 나머지 원문 보존 (슬라이스4 호출)
│   │
│   ├── morph/                       # [M3] 표면구동 내부 모핑 (numpy/scipy)    — 슬라이스 4
│   │   ├── laplacian.py              #   build_laplacian + morph_laplacian (변위장 조화확장)
│   │   ├── rbf.py                    #   morph_rbf (TPS, 경계노드 B 기준 O(B³))
│   │   ├── quality.py                #   check_quality (Jacobian 부호반전 + aspect)
│   │   └── driver.py                 #   morph_phone_volume: 증분+게이트, 실패시 거부/RBF
│   │
│   ├── hand/                        # [M2] 손 로더                            — 슬라이스 2
│   │   ├── makehuman.py              #   MakeHumanLoader (단일 클래스, Protocol 없음)
│   │   └── types.py                  #   RiggedHand dataclass (값 스키마 고정)
│   │
│   ├── blender_core/               # bpy 전용. headless 진입점.              — 슬라이스 2~4
│   │   ├── dispatch.py               #   COMMANDS dict + run_command (와이어 디스패처)
│   │   ├── hand_ops.py               #   load_hand, pose_hand, set_pose (batch)
│   │   ├── grip_ops.py               #   blendshape 프리셋 + shrinkwrap 1패스 (자동IK 아님)
│   │   ├── contact_ops.py            #   penetration/contact 측정 (bvhtree)
│   │   ├── io_ops.py                 #   import_stl/export_stl (단위 스케일 적용)
│   │   └── runner.py                 #   headless: argv→dispatch→.blend저장→result.json
│   │
│   ├── app/                         # 파이프라인·세션 (얇음)                  — 슬라이스 5
│   │   ├── pipeline.py               #   run_steps: 함수 리스트 순차 실행, 첫 실패 중단
│   │   ├── session.py                #   GripState 디스크 영속 (단순 JSON)
│   │   └── blender_io.py             #   run_headless(cmd_dict)->result_dict (subprocess)
│   │
│   ├── mcp_server/                  # MCP 도구 표면 (얇은 래퍼)               — 슬라이스 1~5 감쌈
│   │   ├── server.py                 #   FastMCP 엔트리 + @mcp.tool (flat 인자)
│   │   ├── schemas.py                #   Pydantic enum(Finger/GripStyle/...) + 출력 dict
│   │   └── hints.py                  #   에러→자가수정 hint 빌더
│   │
│   └── cli/main.py                  # 배치 CLI (동일 코어)                    — 슬라이스 5
└── tests/
    ├── test_parser.py  test_classify.py  test_faces.py  test_surface.py
    ├── test_boundary.py  test_morph.py  test_quality.py  test_rewrite.py
    └── fixtures/                     # 합성 hex/tet/wedge/pyramid 1요소 + 실파일 회귀
```

검증 반영: `pipeline/` 별도 모듈·`StageResult[T]` 제네릭·`mano_stub.py`·`persist.py`(.npz)·`strategy.py`(Strategy 클래스)·`version_guard.py`·`blender_adapter/`(ABC+소켓) — 전부 제거하거나 해당 슬라이스로 연기. 신규 추가: `classify.py`(degenerate 분류), `boundary.py`(비conformal 외부경계 추출 — 실측 결함 대응).

---

## 3. 채택 디자인 패턴 — 검증 통과한 것만

PLAN/결정사항이 "디자인 패턴을 제대로 적용"을 요구하나, 검증 합의는 **두 번째 구현이 코드로 실재할 때만 패턴을 도입**한다. 그 기준을 통과한 것만 남긴다.

| 패턴 | 적용 위치 | 푸는 구체적 문제 | 도입 시점 |
|------|----------|----------------|----------|
| **Strategy** | `morph/` Laplacian↔RBF | 동일 입출력 계약, 다른 수치. 두 구현 실재. **단 §7에서 우선순위 재결정.** | 슬라이스 4 |
| **Adapter** | `app/blender_io` headless↔socket | 동일 의미호출을 두 실행환경에. **두 번째 구현(소켓)이 코드로 들어올 때** 추출. | 슬라이스 5 |

**패턴 라벨을 떼고 평범한 코드로 부르는 것 (검증 합의 — 라벨이 곧 과설계 신호).**

| 무엇 | 어떻게 | 왜 패턴 아님 |
|------|--------|-------------|
| MCP 도구 함수 | 그냥 `async def` | "Facade"라 부르면 클래스 계층을 만들기 시작 |
| `run_steps` 순차 실행 | 20줄 for-loop | "Pipeline 패턴"이 아니라 공유 러너 함수 |
| `GripState.save/load` | JSON 직렬화 | undo/caretaker 없음 → "Memento" 아님 |
| `StageResult` | 평범한 dataclass | 단일 결과 봉투, 제네릭 없음 |
| 손 로더 | `MakeHumanLoader` 클래스 1개 | 구현 1개뿐 → Protocol/Strategy 미도입. MANO는 제외 확정(PLAN §6) |
| morph 폴백 | `driver.py`의 if 한 줄 | "폴백 프레임워크화" 아님 |
| 백엔드 선택 | `if mode=="socket"` 1줄 | "Factory" 아님 — 슬라이스 5에서 인라인 |
| `COMMANDS` dict | 와이어 직렬화의 일부 | "Command 객체"(execute/undo) 아님. 프로세스 경계용 데이터 |

**명시적 비채택 (변함없음):** Factory(Method/Abstract), GoF Command 객체, Chain of Responsibility, 폴백 프레임워크화. 근거: undo/큐/런타임 플러그인 등록이 없고 고정 시퀀스라서.

---

## 4. 핵심 인터페이스 시그니처

### 4.1 단일 결과 봉투 (`core/result.py`)

```python
# core/result.py — 단계 산출물과 진단을 함께 운반하는 단일 봉투. mcp를 import하지 않는다.
from dataclasses import dataclass, field

@dataclass
class StageResult:
    ok: bool
    artifacts: dict = field(default_factory=dict)   # 논리명 -> 절대경로
    diagnostics: dict = field(default_factory=dict) # {"watertight":True, "min_jacobian":0.31}
    message: str = ""

    @classmethod
    def fail(cls, msg, **diag):
        return cls(ok=False, diagnostics=diag, message=msg)

# 규칙: 예측 가능한 도메인 실패(비watertight, 음 Jacobian, 관통)는 ok=False.
#       진짜 IO깨짐/버그는 예외 raise. 둘을 섞지 않는다. Generic[T]·to_mcp() 없음(검증 P1).
```

### 4.2 메쉬 자료구조 + degenerate 분류 (`dyna_io/model.py`, `classify.py`)

검증 A1·P3 반영: tet/wedge/pyramid가 8슬롯에 **노드 반복(degenerate)**으로 저장됨이 실측 확인됨(ex02 PID 2 = `n1 n2 n3 n4 n4 n4 n4 n4` 류, 고유노드 4). 분류는 고유노드수 **+ 반복 위치 패턴**으로.

```python
# dyna_io/model.py — .k 파싱 결과. 원본 NID/연결성/degenerate 원형 보존(모핑 입력).
from dataclasses import dataclass, field
from enum import Enum
import numpy as np

class ElementType(Enum):
    TET4=4; PYRAMID5=5; WEDGE6=6; HEX8=8; TRI3=103; QUAD4=104; INVALID=-1

@dataclass
class SolidElement:
    eid: int; pid: int
    node_ids: list          # 원형 8슬롯 (degenerate 반복 유지 → .k 복원용)
    etype: ElementType

@dataclass
class ShellElement:
    eid: int; pid: int; node_ids: list; etype: ElementType

@dataclass
class MeshData:
    nodes: dict = field(default_factory=dict)        # NID -> (x,y,z)
    node_constraints: dict = field(default_factory=dict)  # NID -> (tc,rc)  ← 검증 A3
    solids: list = field(default_factory=list)
    shells: list = field(default_factory=list)
    parts: dict = field(default_factory=dict)
    src_path: str = ""                               # 원본 .k 경로(재파싱 source-of-truth)

    def dense_index(self):
        # (X(N,3), nid2row, row2nid). 요소가 참조하는 노드만(고립노드 제외, 검증 G3).
        # driver가 1회 생성해 morph 전 구간 공유(검증 A3).
        ...

# dyna_io/classify.py — 8슬롯 노드 반복 패턴으로 솔리드 타입 판정 (검증 A1·P3)
def classify_solid(n8: list[int]) -> ElementType:
    u = list(dict.fromkeys(n8))                       # 순서보존 고유 노드
    return {4: ElementType.TET4, 5: ElementType.PYRAMID5,
            6: ElementType.WEDGE6, 8: ElementType.HEX8}.get(len(u), ElementType.INVALID)
    # 주의: PYRAMID5(고유5) vs degenerate-wedge 모호 케이스는 반복 위치로 구분.
    #       합성 fixture에 실제 LS-DYNA 반복 규약(어느 슬롯이 어디와 같은지) 반영.
```

### 4.3 자유면 추출 + 외부경계 (`dyna_io/faces.py`, `boundary.py`)

검증 P1·B1·B2·D1 반영 (실측: tet 메쉬가 face-conformal 아님 → 자유면 9600개 중 1040개만 진짜 외곽, 8560개가 내부 가짜면).

```python
# dyna_io/faces.py — 면 추출. winding은 표를 믿지 않고 반대편 노드로 외향 강제.
def solid_faces(el: SolidElement) -> list[tuple]:
    # 고유노드 기반 면 표(TET4=4면, HEX8=6면, WEDGE6=5면, PYRAMID5=5면).
    # degenerate hex의 collapse된 quad는 tri로 환원(중복 면 방지, 검증 B2).
    ...

def extract_free_faces(elements, nodes) -> list[tuple]:
    bucket = {}                                       # frozenset(노드) -> [(el, ordered)]
    for el in elements:
        for fn in solid_faces(el):
            bucket.setdefault(frozenset(fn), []).append((el, fn))
    free = [occ[0] for occ in bucket.values() if len(occ) == 1]
    n3plus = sum(1 for occ in bucket.values() if len(occ) >= 3)  # 비conformal 진단(검증 B2)
    return free, {"non_conformal_faces": n3plus}

def orient_outward(face_nodes, el, nodes) -> tuple:
    # 검증 D1: 센트로이드가 아니라 "면에 없는 반대편 요소 노드"로 외향 판정.
    #          degenerate 요소에서도 안정적(센트로이드는 collapse 시 불안정).
    ...

# dyna_io/boundary.py — 비conformal 메쉬에서 진짜 외부 표면만 추출 (검증 P1 — 핵심 신규)
def outer_boundary(free_faces, nodes) -> tuple[list, set]:
    """자유면 중 외부 connected-component만 반환.
    tet 비conformal 메쉬는 내부에 떠 있는 가짜면(8560개)을 만든다 —
    이들을 모핑 Dirichlet 경계에서 제외해야 경계조건이 오염되지 않는다.
    전략: (a) 좌표 기반 노드 weld 후 면 재해싱, 또는
          (b) 외향법선·bbox 기반 외부 셸 connected-component 선택.
    returns (boundary_faces, boundary_nids)."""
    ...
```

### 4.4 모핑 (`morph/driver.py`) — 변위장 조화확장, 거부 우선

검증 P2·P4·P5·C1 반영 (실측: 두께 40% 압입에서 Laplacian inversion, RBF는 같은 압입을 **더 못 견딤** — RBF가 회전엔 강하나 압입엔 무력).

```python
# morph/laplacian.py — 변위장 u의 조화확장. 좌표가 아니라 변위를 푼다(검증 P4).
def build_laplacian(X, edges_by_unique_nodes, inverse_dist=True):
    # 그래프 라플라시안 L. 가중 1/|xi-xj|, epsilon 가드(degenerate 0거리, 검증 D4).
    # 엣지는 반드시 unique_nodes 기반(collapse 자기엣지 배제).
    ...

def morph_laplacian(X, elems, bnd_idx, bnd_disp):
    # L_II u_I = -L_IB u_B, scipy spsolve 다중 rhs(3축). X' = X + u.
    # 내부노드 0개면 no-op 단락(단일요소/셸-only, 검증 D2).
    ...

# morph/driver.py — 게이트+증분, 실패시 "거부 우선"(폴백 아님, 검증 P2/P5/B3)
from core.result import StageResult

def morph_phone_volume(mesh, edited_outer_stl, n_steps=8, max_substeps=6) -> StageResult:
    """1) phone_orig 재파싱 → dense_index 1회 생성(검증 A3)
       2) outer_boundary 노드 ↔ 편집외곽 STL: cKDTree 되투영으로 bnd_disp(검증 P6/A1)
          — sidecar 인덱스 매핑은 Blender STL 왕복 시 무효 → 항상 공간매칭
       3) LaplacianMorph 증분 적용, 게이트 실패 스텝은 이분(max_substeps 한계)
       4) 한계 도달 시: 기본은 거부(ok=False) + 변위축소 hint.
          RBF는 '폴백'이 아니라 '비연결/큰회전 입력용 대안'으로만 호출(method='rbf' 명시 시).
       5) 성공 시 rewrite_k 호출
       실패 = StageResult.fail(min_jacobian=..., inverted=[...]). MorphFailure 예외는 버그용만."""
    ...
```

### 4.5 손 로더 (`hand/types.py`, `makehuman.py`) — 단일 클래스, 값 스키마 고정

검증 P6(과설계)·C3(값 스키마) 반영: Protocol/dict디스패치/stub 제거. RiggedHand 값 타입 고정.

```python
# hand/types.py — 손 로더가 그립에 제공하는 공통 계약. 값 타입을 고정해 독립 구현 충돌 방지.
from dataclasses import dataclass, field

@dataclass
class RiggedHand:
    object_name: str                              # bpy.data.objects 키
    armature_name: str
    finger_chains: dict = field(default_factory=dict)  # {"index": [bone names root→tip]}
    blendshapes: dict = field(default_factory=dict)    # {"fist": shape_key_name, ...}

# hand/makehuman.py — CC0 FBX + Rigify 본 매핑. MANO 추가 시 여기에 클래스 하나 더(YAGNI).
class MakeHumanLoader:
    def __init__(self, asset_path="assets/hands/makehuman_right.fbx", handedness="right"):
        ...
    def load(self, run_headless) -> RiggedHand:
        # finger_chains/blendshapes는 슬라이스2의 '실제 FBX 본 트리 덤프'로 채운다 —
        # 설계 시점에 f_index.01.R로 못박지 않는다(검증 P12). 덤프 결과를 assets/LICENSE 옆에 기록.
        ...
```

### 4.6 파이프라인 + 세션 (`app/pipeline.py`, `session.py`)

```python
# app/pipeline.py — 함수 리스트를 순차 실행, 첫 실패 중단. 프레임워크 아님(검증 P2).
def run_steps(steps, ctx) -> "StageResult":
    last = None
    for step in steps:                            # step(ctx) -> StageResult
        last = step(ctx)
        if not last.ok:
            return last
        ctx.update(last.artifacts)
    return last

# app/session.py — 그립 세션 상태를 디스크 JSON으로 영속. 메모리 캐시 없음(검증 P4 — 디스크 직독).
from pydantic import BaseModel, Field
from enum import Enum
from pathlib import Path

class PhoneStage(str, Enum): EMPTY="empty"; EXTRACTED="extracted"; MORPHED="morphed"
class HandStage(str, Enum):  NONE="none"; LOADED="loaded"; GRIPPED="gripped"

class FingerPose(BaseModel):                       # 관절 분해는 슬라이스2 리그 덤프 후 확정(검증 P4/D3)
    flex: float = Field(0.0, ge=0, le=1)          # 단일 굴곡 스칼라로 시작(coupled curve는 프리셋이 보유)
    spread: float = Field(0.0, ge=-1, le=1)

class GripState(BaseModel):
    session_id: str
    workdir: str
    phone_stage: PhoneStage = PhoneStage.EMPTY     # 폰/손 병렬 트랙(검증 B1/B2 — 단일 enum 직렬화 금지)
    hand_stage: HandStage = HandStage.NONE
    channel: str = "headless"                       # 세션 불변(검증 G3 — 호출마다 바꾸지 않음)
    grip_style: str = "natural"
    handedness: str = "right"
    fingers: dict[str, FingerPose] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)

    def save(self): (Path(self.workdir)/"state.json").write_text(self.model_dump_json(indent=2))
    @classmethod
    def load(cls, wd: Path): return cls.model_validate_json((wd/"state.json").read_text())
```

### 4.7 MCP 입력 스키마 (`mcp_server/schemas.py`) — flat 인자

검증 A1(치명) 반영: 단일 Pydantic 모델 래핑은 inputSchema를 `{"args": {...}}`로 중첩시켜 LLM flat 호출과 모순됨(실측). **flat 개별 인자**로 노출, enum만 Pydantic 강제.

```python
# mcp_server/schemas.py — enum으로 LLM 입력을 강제(환각 봉쇄). 도구는 flat 인자(검증 A1).
from enum import Enum

class Finger(str, Enum): thumb="thumb"; index="index"; middle="middle"; ring="ring"; pinky="pinky"
class GripStyle(str, Enum): natural="natural"; tight="tight"; pinch="pinch"; edge_hold="edge_hold"; flat_palm="flat_palm"
class Handedness(str, Enum): left="left"; right="right"
class MorphMethod(str, Enum): laplacian="laplacian"; rbf="rbf"

# 출력은 공통 dict(BaseModel 아님): {ok, session_id, phone_stage, hand_stage, message,
#   artifacts:{논리명->절대경로}, metrics:{faces,watertight,min_jacobian,penetration_mm}, hint?}
# 코어 StageResult를 이 dict로 변환하는 곳은 MCP 도구뿐(코어는 mcp 무관).
```

---

## 5. MCP 도구 카탈로그 + 자연어 시나리오

검증 P3·P4·D1 반영: 도구를 7개로 축소, flat 인자, 세션은 암묵 생성 가능, 채널은 세션 불변. `render_preview`/`export_hand_stl`/`run_full_pipeline`/Resources/Prompts는 슬라이스 5로 연기.

| 도구 | 설명 | 주요 인자(flat) | stage 전제 |
|------|------|----------------|-----------|
| `extract_surface` | .k → 외곽 STL + 원본 보존 | `k_file, session_id?, parts?, merge_shells=True` | (암묵 생성) |
| `inspect_k` | PART 목록·요소타입·watertight 진단 (자가수정 관찰용, 검증 E2) | `k_file` | 없음 |
| `load_hand` | MakeHuman 손 로드 | `session_id, handedness=right, hand_asset?` | phone≥extracted |
| `grip_phone` | 스타일 프리셋 그립 (blendshape+shrinkwrap, 자동IK 아님) | `session_id, style=natural` | hand=loaded |
| `adjust_finger` | "약지 더 굽혀" — 델타 누적 (batch set_pose) | `session_id, finger, delta_flex, delta_spread` | hand=gripped |
| `morph_phone` | 편집 외곽을 체적 메쉬에 전파 | `session_id, edited_outer?, method=laplacian, scale=1.0` | phone≥extracted |
| `export_solid_k` | 모핑 결과 .k (좌표만 패치) | `session_id, out_path?` | phone=morphed |

설계 포인트.
- `inspect_k`는 검증 E2 해소. watertight 실패 시 LLM이 PART ID를 환각하지 않고 실제 목록을 본다.
- `adjust_finger`는 검증 P9 반영: 매 호출 콜드스타트를 피하려 **batch `set_pose`**로 여러 조정을 한 subprocess에서 처리. 슬라이스 5 소켓 채널이 들어오면 즉시 반영.
- `grip_phone`은 검증 P11 반영: "자동 수렴 IK" 환상 제거. blendshape 프리셋(GripStyle enum) + per-finger shrinkwrap 1패스 + penetration 리포트.

### 시나리오 A — "이 폰 .k 오른손으로 쥐고 약지 더 굽혀서 솔리드 .k 뽑아줘"

```
1. extract_surface(k_file="/data/phone/phone.k")
   → {ok, session_id:"grip-7f3a", phone_stage:"extracted",
      metrics:{faces:18420, watertight:1}, artifacts:{phone_outer, phone_orig}}
2. load_hand(session_id="grip-7f3a", handedness="right")  → {hand_stage:"loaded"}
3. grip_phone(session_id="grip-7f3a", style="natural")
   → {hand_stage:"gripped", metrics:{penetration_mm:0.2}, artifacts:{phone_edited_outer}}
   (그립 접촉으로 폰 외곽이 손가락 자리만큼 함몰 → phone_edited_outer.stl 생성)
4. adjust_finger(session_id="grip-7f3a", finger="ring", delta_flex=0.2)  # "약지 더 굽혀"
   → {metrics:{penetration_mm:0.3}}
5. morph_phone(session_id="grip-7f3a", method="laplacian")  # 입력=phone_edited_outer
   → {phone_stage:"morphed", metrics:{min_jacobian:0.41}}
6. export_solid_k(session_id="grip-7f3a", out_path="/data/phone/phone_gripped.k")
```

### 시나리오 B — 자가수정: 비watertight + morph inversion

```
1. extract_surface(k_file="/data/mixed/case.k")  → {ok:false, metrics:{watertight:0},
     hint:"watertight 아님. inspect_k로 PART별 상태를 보고 셸 PART를 parts에 포함하세요."}
2. inspect_k(k_file="/data/mixed/case.k")  → {parts:[{pid:1,type:HEX8,wt:1},{pid:5,type:SHELL,open:1}], ...}
3. extract_surface(k_file="/data/mixed/case.k", parts=[1,2,5])  → {ok:true, watertight:1}
   ... grip ...
4. morph_phone(session_id=..., method="laplacian")
   → {ok:false, metrics:{min_jacobian:-0.08},
      hint:"요소 뒤집힘. scale=0.5로 변형을 줄이세요. 그래도 실패 시 그립을 완화(adjust_finger 굴곡↓)."}
   # 주의: RBF는 압입 inversion을 더 못 고침(실측) → hint가 RBF가 아니라 변형축소/그립완화를 우선 제안.
5. morph_phone(session_id=..., method="laplacian", scale=0.5)  → {ok:true, min_jacobian:0.22}
```

검증 P2/C2 반영: morph 실패 hint가 "RBF로 폴백"이 아니라 **변형량 축소 우선**이다. RBF는 회전 지배 입력에만 권한다.

---

## 6. 상태 모델 — 폰/손 병렬 트랙

검증 B1/B2 반영 (단일 stage enum이 손·폰 병렬 트랙을 직렬화하는 결함).

```
phone_stage:  EMPTY ──extract──▶ EXTRACTED ──morph──▶ MORPHED
hand_stage:   NONE  ──load────▶ LOADED   ──grip───▶ GRIPPED
                                              │
연결점:  grip 또는 GUI 편집이 phone_edited_outer.stl 생성 → morph_phone 입력
```

- 두 트랙은 독립적으로 전진한다. `grip_phone`은 `phone_edited_outer.stl`을 부산물로 만들고, `morph_phone`이 그걸 입력으로 쓴다 — 이것이 유일한 트랙 간 데이터 연결이다.
- **단계 후퇴 무효화 (검증 B1):** `extract_surface` 재호출 시 `phone_stage=EXTRACTED`로 후퇴하고 하위 산출물(`phone_morphed.k`)을 stale로 표시·삭제. `adjust_finger`는 `hand_stage=GRIPPED` 정확 일치를 요구(morph 후 호출 거부).
- **단위 정규화 (검증 E1 — 손/폰 1000배 불일치):** `.k`는 단위 무차원이나 좌표 스케일로 mm 추정(실측 ex02 좌표 0~85 = mm 스케일). 손(MakeHuman, m 단위)은 `load_hand`에서 **1000배 스케일**로 mm 정렬. 스케일 팩터를 GripState에 기록. ContactState "mm"는 이 정규화 후에만 유효.
- **동시성 (검증 D2/F4):** 세션별 파일락(`state.json.lock`)으로 read-modify-write 보호. 소켓 채널 멀티세션은 슬라이스 5에서 세션별 .blend 격리로 해결(지금은 headless라 무관).

---

## 7. 모핑 수치 설계 — inversion 정면 대응

검증 P2/P4/P5/C1/C3가 실측으로 입증한 핵심 리스크: **단순 선형 모핑은 흔한 grip dent에서 inversion을 낸다.**

**1. 변위장 조화확장 (좌표 스무싱 아님).** `u`에 대해 `L u = 0`, `u[bnd]=bnd_disp` 풀고 `X' = X + u`. 좌표 자체에 `L X'=0`을 풀면 내부가 붕괴함(검증 P4) — 명시적으로 금지.

**2. 증분의 한계 인정.** 선형 조화확장은 스케일에 선형이라, 전체가 뒤집히면 1/8씩 적용해도 같은 위치에서 뒤집힌다(검증 P5). 증분이 의미를 가지려면 **매 스텝 변형된 메쉬에서 Laplacian 재조립**(준-비선형). `driver.py`가 이를 수행하되, `max_substeps=6`(1/64) 한계로 무한루프 방지(검증 D3).

**3. RBF 우선순위 재결정 (실측 역전).** 실측: 같은 압입에서 RBF(TPS)가 Laplacian보다 **먼저** 살아남지만(d=0.5에서 Lap inverted, RBF +0.00025), 둘 다 깊은 압입(d≥0.6)에선 실패. 회전 지배(twist 120°)는 둘 다 inv 0. 결론:
- **압입(폰 그립의 주 시나리오):** Laplacian 증분 → 실패 시 **거부 + 변형축소**가 정직(RBF 폴백 아님).
- **회전/비연결 입력:** RBF를 명시적 대안으로(`method="rbf"`).
- Strategy 패턴은 유지하되 "런타임 자동 폴백" 정당화는 약화 — 두 방법은 **다른 입력 유형용**이다.

**4. RBF 비용 (검증 B5).** TPS는 **경계노드 B 기준 O(B³)**(전체 N 아님). B가 수천 넘으면 경계 다운샘플 또는 거부. 실파일 183MB 케이스는 B 사전 체크.

**5. 품질 게이트 (검증 C3/B2):** `ok` 판정 = min Jacobian > 0 **AND** aspect ratio 임계 **AND** min/max-Jacobian-ratio. hex는 8 적분점 전부 검사. 부호는 절대값이 아니라 **원본 대비 sign flip**으로 invert 판정(원본이 음수 컨벤션일 수 있음).

---

## 8. Blender 어댑터 설계 — 두 인터프리터 경계

검증 P1(feasibility)·P2·B2 반영 (실측: Blender 4.5.11 LTS / Python 3.11, MCP 서버 Python 3.10 — **다른 인터프리터**).

**프로세스 경계 (불변).** `mcp_server`/`app`(3.10)과 `blender_core`(3.11)는 **반드시 별도 프로세스**. 경계를 넘는 데이터는 **dataclass 공유 import 금지, 순수 JSON dict + 명시적 (de)serialize만**(검증 P1). dataclass는 각 프로세스가 자기 쪽에서만 쓴다.

**슬라이스 1~4 = headless 단일 채널 (검증 P3/P5).**
```python
# app/blender_io.py — headless: blender -b -P runner.py -- cmd.json blend result.json
def run_headless(cmd: dict, workdir: Path) -> dict:
    # 1) cmd.json 쓰기.  2) snap blender 실행.  3) result.json 회수(stdout 파싱 금지).
    # 검증 P2: 결과는 result.json 파일로만 회수 — snap 애드온 로그가 stdout 오염.
    # 검증 B2: 러너는 .py 경로로 넘김(-m 플래그 비실재). --factory-startup으로 애드온 비활성.
    # 검증 C3(gaps): stderr는 별도 스레드/communicate()로 드레인(deadlock 방지).
    ...
```
- `DTS_BLENDER_BIN` 미설정 시 명시적 에러(검증 B1). snap blender 4.5.11 LTS는 자동갱신 트랙이라 "핀"이 아니라 **`(4,5)` 범위 가드**(검증 P14). `snap refresh --hold blender` 권장.
- bpy 버전 가드는 `runner.py` 진입부 `bpy.app.version[:2] == (4,5)` assert 한 줄(검증 P6 — 전용 모듈 불필요). STL import op은 4.5 이름(`wm.stl_import`) 하드코딩(단일버전이라 분기 불요).

**슬라이스 5에서 소켓 추가.** GUI 상주 애드온(`bpy.app.timers` 메인스레드 디퍼) + 소켓 서버. 프레이밍은 **개행 구분 JSONL 또는 4바이트 길이 프리픽스**(검증 P6/C2 — "프리픽스 없이 누적 파싱" 금지). 이때 `run_headless`와 동일 `(op, params)` 계약을 만들어 Adapter를 추출한다(두 구현 실재 → 정당).

**MCP long-running (검증 P10/A3).** morph가 분 단위면 동기 도구 + `ctx.report_progress`가 클라이언트 타임아웃과 충돌. headless subprocess는 **워커 스레드(`anyio.to_thread.run_sync`)**로 오프로드(이벤트 루프 블록·`from_thread.run` RuntimeError 방지, 검증 A3). 슬라이스 4 검증 후 morph 소요시간 측정 → 길면 `morph_phone`만 시작/폴링 패턴으로.

---

## 9. 슬라이스별 구현 순서 + 검증 게이트

| 슬라이스 | 구현 | 검증 게이트 |
|---------|------|------------|
| **0 셋업** | 패키지 레이아웃, `core/result.py`, `pyproject.toml`(numpy/scipy/pytest) | import 통과, 빈 pytest 수집. **trimesh 보류**(검증 P13 — numpy+cKDTree로 충분, 필요 시 추가) |
| **1 DYNA→STL** | `dyna_io/*`(rewrite 제외) + `boundary.py` | 합성 fixture 12종 + 실파일 회귀. **단, watertight는 하드 게이트 아님**(검증 P1) — tet은 비conformal이라 `outer_boundary`가 외부셸을 뽑고 watertight를 진단으로만 보고. `test_real_tet4`가 PID별 ElementType(2→TET4,1·3→HEX8) 단언(검증 F2). → 사용자 게이트 |
| **2 손 로드** | `blender_core/{dispatch,hand_ops,io_ops,runner}`, `hand/*`, `assets/` | headless load_hand→본회전→export STL. **선행: 실제 FBX 본 트리 덤프**(검증 P12)로 finger_chains 확정. 단위 1000배 스케일 확인(검증 E1) |
| **3 그립** | `blender_core/{grip_ops,contact_ops}` | blendshape 프리셋 + shrinkwrap 1패스 → penetration 리포트. **자동수렴 IK는 비목표**(검증 P11). phone_edited_outer.stl 산출 확인 |
| **4 모핑** | `morph/*` + `dyna_io/rewrite.py`(이때 작성, 검증 P10) | 게이트 통과(Jacobian>0+aspect). 압입 inversion 시 거부+축소 hint. rewrite_k 라운드트립(재파싱 노드수·요소수 동일). **좌표 오버플로 테스트**(검증 P7/B4). LS-DYNA init-check 가능 시 |
| **5 CLI+GUI+MCP** | `app/*`, `cli/main.py`, 소켓 애드온, `mcp_server/*` | end-to-end 1커맨드, CLI≡GUI. MCP flat 인자 inputSchema 확인(검증 A1). 소켓 멀티세션 격리 |

`rewrite.py`는 슬라이스 4로 이동(검증 P10 — 슬라이스 1과 무관). `persist.py`(.npz) 제거 — 원본 `.k` 경로를 들고 재파싱(검증 P11).

---

## 10. 검증 반영 요약 — 무엇을 빼고 무엇을 채웠나

**뺀 것 (과설계).**

| 항목 | 조치 | 근거 |
|------|------|------|
| 수직 L1~L4 계층 + 불변식 메타룰 | PLAN 수평 모듈로 | YAGNI, import 규칙 1줄로 충분 |
| `BlenderBackend` ABC + SocketBackend + factory | 슬라이스 5로. headless는 `run_headless` 함수 | 두 번째 구현 부재 |
| 패턴 7개 라벨 (Facade/Pipeline/Memento/Command/Factory/Result/손Strategy) | 라벨 제거, 평범한 코드로 | "패턴을 위한 패턴" |
| `StageResult[T]` 제네릭 + `to_mcp()` + `ToolResult` 이중봉투 | 단일 dataclass, MCP에서만 dict화 | 레이어 침범, 변환 보일러플레이트 |
| `pipeline/` 모듈 + `Stage` 타입 | `run_steps` 20줄 함수 | "얇은 래퍼" |
| `mano_stub.py`, `persist.py`(.npz), `strategy.py`(클래스), `version_guard.py` | 제거/인라인 | 죽은코드·중복·단일상수 |
| `render_preview`/`export_hand_stl`/`run_full_pipeline`/Resources/Prompts | 슬라이스 5로 | 핵심 산출물 아님 |
| 단일 Pydantic 모델 래핑(`args:`) | flat 개별 인자 | inputSchema 중첩이 LLM 호출과 모순(실측) |

**채운 것 (gaps).**

| 항목 | 추가 | 근거 |
|------|------|------|
| 모핑 입력원 미정의 (최대 공백) | phone_edited_outer.stl = 그립/편집 산출 (PLAN §3) | B1/A1/A2 |
| tet 비conformal 자유면 | `boundary.py` 외부셸 connected-component | P1 실측 |
| degenerate hex 분류 | `classify.py` 고유노드수+반복패턴 | A1/P3 실측 |
| 손/폰 병렬 트랙 | phone_stage/hand_stage 분리 | B1/B2 |
| 단위 1000배 불일치 | load_hand mm 스케일 정규화 | E1 |
| 자가수정 관찰 도구 | `inspect_k` (PART 목록) | E2 |
| 두 인터프리터 경계 | JSON-only 직렬화 명문화 | P1 feasibility 실측 |
| async 루프 블록 | subprocess를 워커스레드 오프로드 | A3/P10 |
| TC/RC·좌표 오버플로 | node_constraints 보존, 폭 가드 | A3/P7/B4 |

**대안 제시 (실현성).**

| 문제 | 대안 |
|------|------|
| RBF가 압입 inversion을 못 고침(실측) | "폴백" 폐기 → 거부+변형축소 우선, RBF는 회전/비연결 입력 전용 |
| 자동 그립 IK 수렴 환상 | blendshape 프리셋 + shrinkwrap 1패스로 범위 축소 |
| headless 콜드스타트 ≠ 인터랙티브 | adjust_finger batch set_pose, 소켓은 슬라이스 5 |
| snap 자동갱신으로 "4.5 핀" 불가 | `(4,5)` 범위 가드 + `--hold` 권장 |

---

## 11. 잔여 위험 + 미해결 결정 (context-notes.md 갱신 권장)

**미해결 항목 확정 답 (기존 context-notes §미해결 3건 중 2건).**
1. **`.k` 재작성 보존 범위** → 확정: `*NODE`/`*ELEMENT_*`/`*PART`만 파싱, 나머지는 원문 byte 보존. **단 좌표 의존 카드 경고**(검증 P8): `*INITIAL_VELOCITY_GENERATION`/`*DEFINE_COORDINATE_NODES`/`*CONSTRAINED_*`/`*BOUNDARY_PRESCRIBED`는 모핑이 형상을 바꾸면 물리가 틀어짐 → 존재 시 hint로 경고. "무조건 유효"는 거짓.
2. **Blender LTS** → 확정: **4.5.x 범위 가드**(실측 4.5.11). snap 자동갱신이라 단일 버전 핀 불가 → `--hold` 권장.
3. **폰 외곽 편집 UI** → 여전히 미해결. 코어는 `edited_outer_stl` 경로만 입력. GUI 편집(슬라이스 5)과 그립 함몰(슬라이스 3) 두 경로가 모두 이 STL을 채운다.

**잔여 위험 (구현 중 모니터).**
- **모핑이 깊은 압입에서 근본적으로 실패할 수 있음.** 선형 조화확장의 한계(실측). 깊은 dent는 거부가 정직한 출력 — ARAP/비선형은 설계 범위 밖, 필요 시 별도 결정.
- **MakeHuman FBX 본 트리 미확인.** 슬라이스 2 선행 덤프 전까지 finger_chains는 잠정.
- **LS-DYNA init-check 환경 부재 시** rewrite 검증은 재파싱 라운드트립(노드/요소 수·참조 무결성)으로 대체.
- **자유형식(콤마) `.k`·`*NODE %` long format·`*INCLUDE`** 는 현 샘플에 없어 미테스트 → 만나면 명시적 에러(silent 빈 결과 금지).
- **세션 GC/TTL·동시성 락**은 슬라이스 5에서 구체화. 지금은 파일락 + 수동 정리.

---

검증 근거 실파일(절대경로): `/data/ball_drop_test_v3/ex01_hex8_m027_baseline/ex01_hex8_m027_baseline.k`(HEX8 16칸 고정폭 NODE), `/data/ball_drop_test_v3/ex02_tet4_m027_baseline/ex02_tet4_m027_baseline.k`(PID1=144 HEX8, PID2=4000 degenerate-tet, PID3=32 HEX8 — 실측 분류 확인, tet 자유면 9600개 중 2836 non-manifold edge = 비conformal 입증). 환경: snap Blender 4.5.11 LTS / Python 3.11, MCP 서버 Python 3.10.12, `DTS_BLENDER_BIN` 미설정. 기준 문서: `/home/koopark/claude/DigitalTwinSimulation/{PLAN.md,checklist.md,context-notes.md}`.
