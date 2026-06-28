# 그립 세션 상태를 디스크 JSON으로 영속. 폰/손 병렬 트랙(DESIGN §4.6, §6).
from enum import Enum
from pathlib import Path

from pydantic import BaseModel, Field


class PhoneStage(str, Enum):
    EMPTY = "empty"
    EXTRACTED = "extracted"
    MORPHED = "morphed"


class HandStage(str, Enum):
    NONE = "none"
    LOADED = "loaded"
    GRIPPED = "gripped"


class GripState(BaseModel):
    """세션 상태. 폰/손은 독립 트랙으로 전진하며, phone_edited_outer.stl로만 연결된다."""

    session_id: str
    workdir: str
    phone_stage: PhoneStage = PhoneStage.EMPTY
    hand_stage: HandStage = HandStage.NONE
    grip_style: str = "natural"
    handedness: str = "right"
    artifacts: dict[str, str] = Field(default_factory=dict)   # 논리명 -> 절대경로
    src_k: str = ""                                            # 원본 폰 .k (모핑 재파싱용)

    def save(self):
        Path(self.workdir).mkdir(parents=True, exist_ok=True)
        (Path(self.workdir) / "state.json").write_text(self.model_dump_json(indent=2))

    @classmethod
    def load(cls, workdir) -> "GripState":
        return cls.model_validate_json((Path(workdir) / "state.json").read_text())

    @classmethod
    def load_or_create(cls, session_id: str, base_dir: str) -> "GripState":
        wd = Path(base_dir) / session_id
        sf = wd / "state.json"
        if sf.exists():
            return cls.load(str(wd))
        st = cls(session_id=session_id, workdir=str(wd))
        st.save()
        return st
