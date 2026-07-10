# Context Notes — DigitalTwinSimulation

> 작업 중 내린 결정과 그 근거. 다음 세션이 재유도 없이 이어가기 위한 기록.

## 2026-06-26 — 초기 설계

### 결정 1: 솔리드 메쉬는 Blender가 아니라 모핑으로 만든다
- Blender는 표면(B-rep) 도구라 FE 품질 솔리드(tet/hex) 메쉬를 못 만든다.
- 사용자 확인: 폰은 원본 `.k`에 이미 체적 메쉬가 있음 → **새로 tet 생성하지 않고 기존 메쉬를 변형(모핑)**한다.
- 손은 표면만 필요 → 솔리드 핸드오프(TetGen 등) 불필요해짐. 가장 큰 리스크 제거됨.

### 결정 2: 손 모델은 MANO가 아니라 MakeHuman (CC0)
- MANO `.pkl` 파라미터 = MPI 비상업 라이선스. 상업 R&D/제품에 부적합.
- 코드 래퍼가 permissive여도 `.pkl`이 제약 → MANO 전체가 비상업.
- MakeHuman GUI export = CC0 (단 unmodified GUI export 한정; 스크립팅은 AGPL).
- 손 모델 로더는 **인터페이스로 추상화** → 추후 MANO 상업 라이선스 시 교체 가능.

### 결정 3: 모핑 엔진 새로 구현 (KooRemapper 재사용 X)
- KooRemapper는 C++ CLI로 flat↔bent 구조화 메쉬 매핑/프리스트레스 전용. 우리 문제(표면구동 내부 스무싱)와 다름.
- 단, KooRemapper의 `.k` 파서는 검증된 참고 자료 → 포맷 디테일 확인에만 사용.
- 우리 모핑: 경계 변위를 Laplacian/RBF로 내부에 전파.

### 결정 4: 첫 슬라이스 = DYNA→STL 추출기
- 가장 낮은 위험, 모든 후속 단계의 입력. 독립 검증 가능.

## 검증된 사실 (실제 파일 조사)
- 샘플 `.k`: `/data/ball_drop_test_v3/ex02_tet4_m027_baseline/...` (tet4), `ex01_hex8...` (hex8) 등 16종.
- 표면 추출에 필요한 키워드: `*NODE`, `*ELEMENT_SOLID`, `*ELEMENT_SHELL`, `*PART`.
- 나머지(`*CONTROL_*`, `*MAT_*`, `*CONTACT_*`, `*DATABASE_*`)는 STL 추출 시 무시. (단 모핑 후 .k 재작성 시 보존 필요할 수 있음 — 슬라이스 4에서 재검토)
- 배터리/스마트폰 관련 실제 메쉬 다수 존재 (`/data/battery_study/mesh_examples` 등).

## 2026-06-26 — 멀티에이전트 설계(DESIGN.md) + 실측 검증

18-에이전트 워크플로우로 DESIGN.md 작성. 핵심은 **에이전트들이 실제 .k 파일을 읽어 가정을 실측 반증**한 것. 직접 재확인 완료한 실측 사실:

### 실측 확인된 함정 (코드 짜기 전 발견)
- **degenerate-tet 저장**: `/data/ball_drop_test_v3/ex02_tet4...k` PID2의 4000개 tet는 8슬롯 hex 형식에 마지막 노드 반복 저장. 예: `1001 1002 1012 1122 | 1122 1122 1122 1122` (고유 4노드). 순진하게 hex8로 읽으면 면 추출이 망가짐 → `classify.py`(고유노드수+반복패턴) 필수.
- **PART 분포 실측**: ex02 = PID1(144 HEX8) + PID2(4000 degenerate-TET) + PID3(32 HEX8). 한 파일에 hex/tet 혼재.
- **tet 비conformal**: tet 자유면 9600개 중 2836 non-manifold edge → 자유면≠watertight 외곽. `boundary.py`로 외부 connected-component만 모핑 경계로 써야 함. **watertight는 하드 게이트가 아니라 진단으로 강등.**
- **NODE 고정폭 포맷**, 좌표 0~85 = mm 스케일. MakeHuman 손(m단위)과 **1000배 차이** → load_hand에서 mm 정규화.
- **두 인터프리터**: Blender 4.5.11/Python3.11 ≠ MCP서버 Python3.10 → 프로세스 경계는 **JSON dict만**, dataclass 공유 import 금지.

### 설계 교정 (과설계 제거)
- 수직 4계층/불변식 메타룰 → PLAN 수평 모듈 + import 방향 규칙 1줄.
- 패턴 라벨 7개 제거. 살아남는 추상화: **Strategy(morph), Adapter(슬라이스5)** 둘뿐. 나머지는 평범한 함수/dataclass/JSON.
- Blender 백엔드 ABC+소켓 → 슬라이스 5로 연기. 슬라이스1~4는 `run_headless(cmd)` 함수 하나.
- MCP 도구 11→7개, 단일 Pydantic 래핑 → flat 인자(중첩 inputSchema가 LLM 호출과 모순, 실측).

### 모핑 수치 핵심 (실측 기반)
- **변위장 조화확장** (좌표가 아니라 변위 u에 Lu=0). 좌표에 풀면 내부 붕괴.
- **RBF 폴백 폐기**: 실측상 RBF가 압입 inversion을 Laplacian보다 못 고침. 압입(폰 그립 주 시나리오)은 Laplacian 증분→실패시 **거부+변형축소**. RBF는 회전/비연결 입력 전용 대안.
- 증분은 매 스텝 메쉬 재조립해야 의미. max_substeps=6 한계.

## 미해결/추후 결정 (DESIGN §11에서 2건 확정)
- [확정] `.k` 재작성: `*NODE`/`*ELEMENT_*`/`*PART`만 파싱, 나머지 원문 byte 보존. **단 좌표의존 카드(`*INITIAL_VELOCITY_GENERATION`/`*DEFINE_COORDINATE_NODES`/`*CONSTRAINED_*`/`*BOUNDARY_PRESCRIBED`)는 모핑 시 물리 틀어짐 → hint 경고.**
- [확정] Blender 4.5.x 범위 가드(snap 자동갱신이라 단일핀 불가, `--hold` 권장).
- [미해결] 폰 외곽 편집 UI(슬라이스 5). 코어는 `edited_outer_stl` 경로만 입력.

## 2026-06-26 — 손 모델 전략 변경: MakeHuman → Blender 절차적 생성

**실측 탐침 결과 (Blender 4.5.11에서 직접 검증):**
- armature(스켈레톤) 코드 생성 OK (본 체인, 부모-자식)
- 메쉬 프리미티브 + ARMATURE 모디파이어 스킨 OK
- STL export 연산자 = `wm.stl_export` (4.5 확정. `export_mesh.stl`은 4.5에서 제거됨 — DESIGN §8 예측 정확)
- Blender 4.5.11 LTS / Python **3.11.11** 재확인 (MCP venv 3.10.12와 다름 → JSON 경계 필수)

**결정: MakeHuman 대신 Blender API로 손을 절차적으로 생성한다.**
Why: 이 환경에 MakeHuman 미설치 + headless 서버라 GUI export 불가. 절차적 생성이 (1) 완전 포터블(외부 에셋/다운로드 0), (2) CC0 라이선스 걱정 제거(코드가 곧 에셋), (3) 본 구조를 우리가 완전 제어 → finger_chains 하드코딩 문제 자체가 사라짐. 사용자 "포터블하게" 원칙과 정합.
How to apply: `hand/procedural.py`가 metaball/cylinder+skin으로 손바닥+5손가락(각 3관절) 메쉬 생성 + armature 자동 바인딩 + blendshape(open/fist) 생성. `MakeHumanLoader`는 `ProceduralHandBuilder`로 대체(인터페이스 RiggedHand는 유지). 추후 더 사실적 손이 필요하면 OBJ/FBX 임포트 경로를 클래스 하나로 추가(YAGNI).
주의: 절차적 손은 "사실적 디테일"은 낮음. 그립 포즈/접촉/모핑 입력으로는 충분(표면만 필요, FEM 손 내부 불필요 — PLAN 확정). 시각 품질이 중요해지면 슬라이스 5에서 사실적 에셋 임포트 옵션 추가.

## 2026-06-26 — 슬라이스1~2 완료, 슬라이스3 1차 (그립 품질 미흡)

**완료 (실파일/실측 검증):**
- 슬라이스1 DYNA→STL: 48 테스트 통과. ex01/ex02 STL bbox가 원본 .k와 일치. degenerate-tet(PID2 4000개) 정상 처리 — hex 오인 없음. 합성 폰(70×150×8mm hex) watertight=True.
- 슬라이스2 손 빌더: 절차적 손 88×176×22mm, 5손가락×3관절=15본. headless 왕복 OK.
- venv를 **Python 3.13.11**로 재생성(사용자 지시), editable 설치로 PYTHONPATH 불필요.

**버그 잡음 (실측):**
- 손 1000² 폭주(88000mm): build_hand의 unit_scale 스케일 블록에서 hand+arm 둘 다 transform_apply → 부모-자식 스케일 중첩. 수정: 해부학 상수를 mm로 직접 정의, transform_apply 제거. 이제 88mm 정상.
- 그립 위치맞춤: 손바닥 중심(local y≈47)을 폰 중심에 정렬하도록 수정. bbox 교차 확인.

**미흡 (다음 개선 대상):**
- 그립 시각 품질이 "자연스러운 쥠"에 못 미침(렌더 확인). 손가락이 폰을 감싸지 않고 옆에 뜸, 손바닥-손가락 연결 어색, 본 회전축 방향 거칢, penetration=0(접촉 안 됨).
- 개선 필요: (1) 손 형상(손바닥 메쉬 품질, 손가락 곡률), (2) 본 회전축이 굴곡 방향과 정렬, (3) 손가락 끝이 폰 표면에 닿게 위치/스케일, (4) shrinkwrap이 실제 접촉을 만들게.
- 이건 시각 피드백 루프(렌더→조정 반복)가 필요한 튜닝 작업. 멀티에이전트 병렬 개선 권장.

## 2026-07-02 — 실전 검증 1·2번 완료 (실제 배터리 .k)

**대상:** /data/battery_study/mesh_examples/stacked_tier-1.k (7054노드, 솔리드4680 HEX8 + 셸7383 QUAD4 혼합, 61 PART, 실제 배터리 셀 75×72×2mm).

**1번 실전 검증 — 실제 스마트폰(배터리) .k:**
- 파싱/외곽추출 OK (18234삼각형, 불량0, 전극 탭까지 정확).
- **특이행렬 버그 발견·수정:** dense_index가 솔리드+셸 노드 모두 담아 셸전용 1002노드가 Laplacian 그래프에서 고립 → MatrixRankWarning singular → 모핑 불가(scale 낮춰도 실패). 수정: dense_index(solids_only=True), driver가 솔리드 노드만. 실측 없이는 못 잡을 버그.
- 수정 후 scale=1.0 모핑 성공(minJ=0.16). 64 테스트 통과. commit 74b62db push됨.

**2번 재해석 검증 — 솔버 판독 가능성 (LS-DYNA 솔버 부재 → DESIGN §9 대체법):**
- 라운드트립: 노드/솔리드/셸/PART 개수 전부 원본과 동일. 좌표만 3481노드 변경, 연결성 100% 보존.
- 비지오메트리 카드(*MAT_JOHNSON_COOK/*SECTION_SOLID/SHELL/*PART) 원문 보존.
- 좌표 유효성: NaN/Inf/폭오버플로 0, 고정폭 포맷 유지 → 솔버 판독 가능.
- 결론: "재해석 가능한 솔리드 .k"가 실물 혼합 메쉬에서 증명됨.

**주의:** 배터리가 2mm로 얇아 손 그립 압입은 여전히 inversion 경향. 두꺼운 폰이면 여유. 얇은 대상은 scale/그립완화 필요.

## 2026-07-07 — 손 형상 전면 개선 (핵심)

**문제(사용자 지적 "실제 손형상 제대로 되냐"):** 기존 절차적 손이 분리된 실린더/캡슐 마디로,
마디 사이 틈이 벌어지고 손바닥은 납작판, 소시지 묶음처럼 보였음. 렌더로 직접 확인.

**해결: Skin 모디파이어 방식으로 hand_build.py 전면 재작성.**
- 관절 뼈대(정점+엣지, 각 정점에 skin 반경) → Skin 모디파이어 + Subsurf → 연속적 유기적 손가락.
- 척추 2점(WRIST→PALM_LOW→PALM_TOP)으로 분기 분산 → 손바닥 벌크, 가로연결 없음(엉킴 방지).
- 관절 위치에 named 본(palm + finger_XX) + ARMATURE_AUTO 자동가중치 → 매끄러운 굴곡.
- 손끝/너클 반경 테이퍼로 자연스러운 손가락. 엄지는 PALM_LOW 측면에서 대향.
- 계약(RiggedHand object_name/armature_name/finger_chains/blendshapes) 유지 → 그립/파이프라인 무수정 작동.
- 그립 위치 재보정: 새 치수(손바닥반경 24, 너클 y62)에 맞춰 runner._grip_phone arm.location 수정.
- 결과: 진짜 사람 손이 폰 모서리를 감싸는 그립. 84 테스트 통과. commit d8f186f.

**남은 미세 이슈:** 엄지가 폰 앞면에 살짝 관통/납작. 검지-중지 사이 작은 skin 아티팩트. 사소.
**교훈:** 유기적 형상은 실린더 조합이 아니라 Skin+Subsurf(뼈대→표면)가 정석. 절차적+포터블 유지하며 품질↑.

## 2026-07-10 — 감사 잔여 이슈 3종 순차 해결

1. **손 watertight (b633c10)**: Skin 분기점 구멍(경계24+nm4)은 fill_holes/boolean/M2V 전부 실패(실측).
   해결 = 분기 없는 아일랜드 골격(체인별 닫힌 튜브+아일랜드 root) + 비등방 반경(손바닥 넓고 얇게)
   + voxel remesh SDF-union. watertight 0/0, 형상 보존, 물갈퀴 자연 형성.
2. **aspect 게이트 (bdd8de5)**: 절대값이 아니라 원본 대비 성장률(기본 5×) — 얇은층 정상 실메쉬 오탐 방지.
   게이트가 test fixture의 잠복 sliver 오염(pipeline에서 고쳤던 인덱스 버그의 테스트판)을 적발 → 수정.
   튜닝 실측: 정상 함몰 rim 전단 ~4.1×, 병리적 인장 11~41×.
3. **관통 패리티 (342a5c3)**: find_nearest 법선 dot는 모서리에서 flaky(58mm 불가능값) → 레이 패리티로.
   실그립 관통값이 기하 상한(폰 반두께 4mm)에 정확히 수렴.
