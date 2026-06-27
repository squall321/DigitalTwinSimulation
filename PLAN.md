# DigitalTwinSimulation — 손 그립 드롭테스트 자동화 파이프라인 계획

> LS-DYNA `.k` → STL 외곽 추출 → Blender 손 모델 그립 포즈 → 폰 외곽 모핑(내부 메쉬 스무싱) → 재구성된 솔리드 `.k` 산출

## 1. 한 줄 요약

DYNA 메쉬에서 외곽을 따와 STL로 만들고, MakeHuman 기반 리깅 손을 Blender에서 자동으로 스마트폰을 쥐게 포즈한 뒤, 폰의 외곽 편집을 기존 체적 메쉬에 전파(스무싱)하여 재해석 가능한 솔리드 메쉬까지 산출하는 자동화 도구.

## 2. 확정된 의사결정 (사용자 합의)

| 항목 | 결정 | 근거 |
|---|---|---|
| 최종 산출물 | **재메쉬된 솔리드 메쉬까지** (폰 한정) | 사용자 명시 |
| 폰 솔리드 처리 | **기존 체적 메쉬를 모핑** (외곽 기준 내부 스무싱). 새 tet 생성 X | "원안 모델에 메시가 다 있으니까" |
| 손 메쉬 | **표면(skin)만**. 내부 솔리드 불필요 | "손은 내부 필요없고" |
| 손 모델 소스 | **MakeHuman (CC0)**. MANO는 비상업 라이선스 문제로 제외 | 라이선스 조사 결과 (아래 §6) |
| 입력 메쉬 타입 | **솔리드/셸/혼합 모두** 지원 | 사용자 명시 |
| 실행 환경 | **headless(bpy) + GUI 둘 다**. 코어 로직은 환경 무관 | 사용자 명시 |
| 모핑 엔진 | **새로 구현 (Laplacian/RBF)**. KooRemapper 재사용 X (단, .k 파서는 참고) | 사용자 명시 |
| 첫 슬라이스 | **DYNA→STL 추출기** | 가장 낮은 위험, 모든 후속 단계의 입력 |

## 3. 아키텍처 (핸드오프 다이어그램)

```
                          ┌─────────────────────────────────────────┐
  DYNA .k (phone) ───────▶│ [M1] dyna_io: 파서                       │
  (*NODE/*ELEMENT_SOLID/  │   - solid 자유면(free face) 추출          │
   *ELEMENT_SHELL/*PART)  │   - shell 직접 표면화                     │──▶ phone_outer.stl
                          │   - 혼합 처리, *PART 단위 분리            │    + 원본 체적 메쉬 보존
                          └─────────────────────────────────────────┘
                                              │
  MakeHuman 리깅 손 ──────┐                   ▼
  (CC0, 1회 export)       │   ┌─────────────────────────────────────┐
                          └──▶│ [M2] blender_core: bpy 라이브러리     │
                              │   - 손 로드 + Rigify/IK 스켈레톤      │
                              │   - blend-shape 모핑(open↔fist, spread)│──▶ hand_posed.stl (표면)
                              │   - 폰 외곽 로드 → 자동 그립 포즈      │    + phone_edited_outer.stl
                              │   - 표면 스무싱/리메쉬                 │
                              └─────────────────────────────────────┘
                                              │ (편집된 폰 외곽)
                                              ▼
                              ┌─────────────────────────────────────┐
  원본 폰 체적 메쉬 ─────────▶│ [M3] morph: 표면구동 내부 스무싱      │
                              │   - 경계 변위 = (편집외곽 - 원본외곽) │──▶ phone_morphed.k
                              │   - Laplacian/RBF로 내부 전파         │    (*ELEMENT_SOLID, 재해석 가능)
                              │   - 요소 품질(Jacobian) 검증          │
                              └─────────────────────────────────────┘
                                              │
                              ┌─────────────────────────────────────┐
                              │ [M4] cli / [M5] gui (얇은 래퍼)       │
                              └─────────────────────────────────────┘
```

핵심 원칙: **Blender는 표면/포즈/모핑의 "지오메트리"만 책임지고, 솔리드 체적 메쉬는 M3가 기존 메쉬를 변형해서 만든다.** Blender 내부에서 솔리드 메쉬를 생성하지 않는다 (불가능/저품질).

## 4. 수직 슬라이스 (구현 순서)

각 슬라이스는 독립적으로 검증 가능하고, 다음 슬라이스의 입력이 된다.

### 슬라이스 1 — DYNA → STL 추출기 [최우선, 진행 중]
- **목표**: 임의 `.k` → watertight 외곽 STL.
- **검증**: `/data/ball_drop_test_v3/*` (tet4/hex8), 셸 포함 `.k`로 추출 → 면 수·watertight 확인. 알려진 형상(공/배터리)으로 육안 검증.
- **세부**:
  1. `*NODE` 파싱 (ID→좌표).
  2. `*ELEMENT_SOLID` (tet4/hex8/pyramid/wedge) → 면 추출, 자유면(한 번만 등장하는 면) = 외곽.
  3. `*ELEMENT_SHELL` (tri3/quad4) → 그대로 표면.
  4. 혼합 메쉬: solid 자유면 + shell 표면 병합.
  5. `*PART` 단위 선택 추출 옵션.
  6. STL(binary/ascii) writer. **원본 체적 메쉬는 별도 보존** (M3가 씀).

### 슬라이스 2 — MakeHuman 손 확보 + Blender 로드
- **목표**: CC0 리깅 손+전완 메쉬를 Blender에 로드, 스켈레톤 작동 확인.
- **검증**: headless `bpy`로 손 로드 → 손가락 본 회전 → STL export. 자세 변경이 메쉬에 반영되는지.

### 슬라이스 3 — 그립 포즈 (IK + blend-shape 모핑)
- **목표**: 폰 외곽 STL 입력 → 손이 자연스럽게 쥐는 포즈 자동 생성.
- **검증**: 슬라이스1 폰 STL + 슬라이스2 손 → 손가락이 폰 표면에 닿되 관통 안 함(접촉 검출). open↔fist 모핑 연속성.

### 슬라이스 4 — 폰 외곽 모핑 (내부 메쉬 스무싱)
- **목표**: 편집된 폰 외곽 → 원본 체적 메쉬를 변형 → 재해석 가능 `.k`.
- **검증**: 경계 변위 전파 후 요소 Jacobian > 0, aspect ratio 임계 이내. LS-DYNA로 로드되는지 (가능하면 `*CONTROL_TERMINATION` 0으로 init check).

### 슬라이스 5 — CLI + GUI 래퍼
- **목표**: headless 배치 CLI와 Blender GUI 애드온이 동일 코어 호출.
- **검증**: 동일 입력 → 동일 출력. CLI end-to-end 1커맨드.

## 5. 기술 스택

- **언어**: Python (Blender bpy가 Python이므로 전체 통일).
- **수치**: numpy, scipy (sparse Laplacian, RBF), 필요시 `trimesh` (STL/표면 연산).
- **Blender**: `bpy` (headless `blender --background --python` + GUI 애드온 공용 코어).
- **손 모델**: MakeHuman 1회 GUI export → CC0 `.obj`/`.fbx` 리포지토리에 동봉.
- **참고만**: KooRemapper의 C++ `.k` 파서 (재사용 아님, 포맷 디테일 검증용).

## 6. MANO 라이선스 조사 결과 (왜 MakeHuman인가)

- MANO 모델 파라미터(`.pkl`)는 **MPI 비상업 과학연구 전용** 라이선스. 상업 제품 incorporation 명시적 금지. 상업용은 `ps-license@tue.mpg.de` 별도 계약 필요.
- 코드 래퍼(manopth=GPL 등)가 permissive여도 **`.pkl`이 poison pill**이라 무관.
- 본 프로젝트는 스마트폰 드롭테스트 = 상업 R&D 맥락 → MANO 부적합.
- **MakeHuman GUI export 산출물 = CC0** (퍼블릭 도메인, 판매·임베드·무저작자표시 가능). 단 unmodified GUI export 워크플로우에서만 CC0 (스크립팅/서버 사용은 AGPL로 복귀) — "1회 export 후 메쉬 동봉" 방식이 이를 충족.
- MANO의 통계적 shape prior(10-dim PCA)는 잃지만, "폰을 자연스럽게 쥐기"에는 리깅 손 + IK + blend-shape 모핑으로 충분.
- 코드는 손 모델 로더를 인터페이스로 추상화 → 추후 MANO 상업 라이선스 확보 시 교체 가능하게 설계.

## 7. 위험 요소 & 대응

| 위험 | 영향 | 대응 |
|---|---|---|
| 혼합 메쉬 자유면 추출 엣지케이스 (degenerate, 공유면) | STL 누수 | 면 해싱 시 정렬된 노드 튜플 키, 단위 테스트로 tet/hex/wedge 망라 |
| 모핑 후 요소 invert (음의 Jacobian) | 재해석 불가 | 변위 스케일링, 품질 게이트, 실패 시 RBF 폴백 |
| 그립 포즈 관통 (손가락이 폰 뚫음) | 비현실적 | Blender collision/shrinkwrap, 접촉 검출 후 IK 조정 |
| Blender 버전별 bpy API 차이 | 깨짐 | 대상 Blender LTS 버전 고정, API 버전 가드 |
| MakeHuman 손 토폴로지가 FEM에 부적합 | 표면 품질 | 표면만 쓰므로 영향 적음; 필요시 리메쉬 |

## 8. 다음 액션

1. `checklist.md`, `context-notes.md` 생성 (이 문서와 함께).
2. 슬라이스 1 (DYNA→STL) 구현 시작 — `dyna_io` 모듈 + 단위 테스트.
3. 슬라이스 1 완료·검증 후 사용자 확인 → 슬라이스 2 진행.
