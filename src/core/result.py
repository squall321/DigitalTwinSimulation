# 단계 산출물과 진단을 함께 운반하는 단일 결과 봉투. mcp를 import하지 않는다.
from dataclasses import dataclass, field


@dataclass
class StageResult:
    """파이프라인 한 단계의 결과.

    규칙: 예측 가능한 도메인 실패(비watertight, 음 Jacobian, 관통)는 ok=False로 표현.
          진짜 IO 깨짐/프로그래밍 버그는 예외를 raise 한다. 둘을 섞지 않는다.
    Generic[T]·to_mcp() 같은 이중 봉투를 만들지 않는다 (DESIGN §4.1).
    """

    ok: bool
    artifacts: dict = field(default_factory=dict)    # 논리명 -> 절대경로
    diagnostics: dict = field(default_factory=dict)  # {"watertight": True, "min_jacobian": 0.31}
    message: str = ""

    @classmethod
    def fail(cls, msg: str, **diag) -> "StageResult":
        return cls(ok=False, diagnostics=diag, message=msg)

    @classmethod
    def success(cls, message: str = "", **kw) -> "StageResult":
        return cls(ok=True, message=message, **kw)
