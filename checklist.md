# Checklist — DigitalTwinSimulation

> DESIGN.md(18-에이전트 설계+실측검증) 반영본. 패턴/MCP/모핑 수치 교정 포함.

## 슬라이스 0 — 프로젝트 셋업
- [x] 요구사항 명확화 (사용자 Q&A)
- [x] MANO 라이선스 조사 → 절차적 손(Blender API)로 전환 (MakeHuman도 불필요)
- [x] 샘플 `.k` 인벤토리 + 포맷 실측 (degenerate-tet, mm스케일, 비conformal 확인)
- [x] PLAN / checklist / context-notes / DESIGN.md 작성
- [x] 패키지 레이아웃 (`src/`, `tests/`, `assets/`, `pyproject.toml`)
- [x] `core/result.py` — StageResult 단일 dataclass (mcp 무관)
- [x] **로컬 venv (Python 3.13.11)** + numpy/scipy/pytest + editable 설치 (포터블)
- [x] import 통과 + pytest 48개 통과

## 슬라이스 1 — DYNA → STL 추출기 (최우선)
- [ ] `dyna_io/model.py`: MeshData/SolidElement/ShellElement/ElementType + node_constraints(TC/RC) 보존
- [ ] `dyna_io/parser.py`: 고정폭 *NODE, *ELEMENT_SOLID/SHELL, *PART (라인 상태머신)
- [ ] `dyna_io/classify.py`: **고유노드수+반복패턴**으로 tet/hex/wedge/pyramid 판정 (degenerate 대응)
- [ ] `dyna_io/faces.py`: solid_faces 표 + extract_free_faces(면해싱) + orient_outward(반대편노드 외향)
- [ ] `dyna_io/boundary.py`: **외부 connected-component 추출** (비conformal 가짜면 제외) ← 신규/핵심
- [ ] `dyna_io/surface.py`: 표면화 + 혼합(solid자유면+shell) 병합
- [ ] `dyna_io/stl.py`: write_stl(binary+ascii) + watertight **진단**(하드게이트 아님)
- [ ] 합성 fixture 12종 (1요소 hex/tet/wedge/pyramid + degenerate)
- [ ] 실파일 회귀: ex02 PID분류 단언 (2→TET4, 1·3→HEX8)
- [ ] CLI: `dyna2stl input.k output.stl [--parts ...]`
- [ ] **사용자 검증 게이트** → 슬라이스 2 승인

## 슬라이스 2 — MakeHuman 손 + Blender 로드
- [ ] MakeHuman 손+전완 export (CC0, 1회) → `assets/hands/` + LICENSE
- [ ] **선행: 실제 FBX 본 트리 덤프** → finger_chains 확정 (설계시 하드코딩 금지)
- [ ] `hand/types.py`: RiggedHand dataclass (값 스키마 고정)
- [ ] `hand/makehuman.py`: MakeHumanLoader (단일 클래스, Protocol 없음)
- [ ] `blender_core/{dispatch,hand_ops,io_ops,runner}.py` (bpy 전용, headless)
- [ ] 검증: load_hand→본회전→export STL. **단위 1000배 mm 정규화 확인**

## 슬라이스 3 — 그립 포즈 ✅
- [x] `blender_core/grip_ops.py`: 프리셋(손가락별 차등 굴곡)+엄지 대향 + 2패스 shrinkwrap
- [x] `blender_core/hand_build.py`: palm 루트본 분리 + 강체 스키닝(마디 부유 해결)
- [x] penetration 측정 (bvhtree) — 한계: 접촉 면적 미측정(추후)
- [x] 검증: 폰 로드 → 그립 → C자 감쌈 렌더 확인 → phone_edited_outer.stl 산출. 48 테스트 통과
- [x] **멀티에이전트 시각루프**(3접근 worktree → 심판 → 승자 A 적용)

## 슬라이스 4 — 폰 외곽 모핑 (내부 스무싱)
- [ ] `morph/laplacian.py`: build_laplacian + morph_laplacian (**변위장 조화확장**, 좌표 아님)
- [ ] `morph/rbf.py`: TPS (경계노드 O(B³), 회전/비연결 전용)
- [ ] `morph/quality.py`: Jacobian **원본대비 sign-flip** + aspect + ratio
- [ ] `morph/driver.py`: 증분+게이트, 실패시 **거부+변형축소**(RBF 폴백 아님). cKDTree 경계 되투영
- [ ] `dyna_io/rewrite.py`: *NODE 좌표만 패치, 나머지 원문 보존. **좌표의존 카드 경고**
- [ ] 검증: 라운드트립(노드/요소 수 동일) + 좌표 오버플로 + (가능시) LS-DYNA init-check

## 슬라이스 5 — CLI + GUI + MCP
- [ ] `app/{pipeline,session,blender_io}.py`: run_steps + GripState(폰/손 병렬트랙) + run_headless
- [ ] `blender_core` 소켓 애드온 (JSONL/길이프리픽스 프레이밍) → **Adapter 추출** (두 구현 실재)
- [ ] `mcp_server/{server,schemas,hints}.py`: FastMCP **flat 인자**, enum 강제, 자가수정 hint
- [ ] 7개 MCP 도구: extract_surface, inspect_k, load_hand, grip_phone, adjust_finger, morph_phone, export_solid_k
- [ ] morph long-running → 워커스레드 오프로드 (async 루프 블록 방지)
- [ ] 검증: end-to-end 1커맨드, CLI≡GUI, MCP inputSchema flat 확인, 자연어 시나리오 A/B
