"""全项目的数据契约（Pydantic 模型），按用途拆成子模块。

为什么拆：一个 240 行的 models 文件，改一处要在长文件里翻；拆开之后
"这个问题属于哪一类"决定了它在哪个文件，`from src.model import Question`
的写法完全不变（本文件统一 re-export）。

```
model/
├─ enums.py     词表：Seniority / MatchLevel / Dimension / QuestionKind / DecideAction
│              + DIMENSIONS + DIMENSION_LABELS
├─ profile.py   输入解析：SkillItem / ProjectItem / ExperienceItem / JDProfile / ResumeProfile
├─ gap.py       缺口分析：GapItem
├─ question.py  出题：Question（含"追问必须引原话"校验）
├─ decision.py  决策：Decision（下一步 + 理由 + 追问）
├─ score.py     评分：Signals / DimensionScore / AnswerScore（valid、avg 自动算）
├─ turn.py      一问一答：Turn
├─ report.py    报告：Strength / Weakness / ReportDraft（模型写）/ Report（代码补齐）
├─ gold.py      评测：GoldItem（人工标注的标准答案，见 src/eval/gold/）
└─ api.py       接口：SessionCreate / SessionCreated / AnswerIn / TurnOut
```

三条约定（改字段前先看这三条）：
1. 枚举值一律用英文标识符。这些值会出现在 model_json_schema() 里 → 拼进
   prompt 给模型看 → 再出现在日志和测试里。中文放在 Field(description=...)
   里，那部分同样会进 prompt，模型照样看得懂。
2. 下游机器要读的字段（分数、枚举、id）必须**必填 + 有范围约束**；给人看的
   长文本（评论、建议、结果）可以给默认值 ""。
3. `Field(description=...)` 不是注释，它是 prompt 的一部分。写含糊了模型就填错。

验收：`python scripts/test_schemas.py` 全绿。
"""

from __future__ import annotations

from .api import AnswerIn, SessionCreate, SessionCreated, TurnOut
from .decision import Decision
from .enums import (
    DIMENSIONS,
    DIMENSION_LABELS,
    DecideAction,
    Dimension,
    MatchLevel,
    QuestionKind,
    Seniority,
)
from .gap import GapItem
from .gold import LEVEL_TO_SCORE, GoldItem, QualityLevel
from .profile import ExperienceItem, JDProfile, ProjectItem, ResumeProfile, SkillItem
from .question import Question, QuestionPlan
from .report import Report, ReportDraft, Strength, Weakness
from .score import AnswerScore, DimensionScore, Signals
from .turn import Turn

__all__ = [
    # enums
    "Seniority",
    "MatchLevel",
    "Dimension",
    "QuestionKind",
    "DecideAction",
    "DIMENSIONS",
    "DIMENSION_LABELS",
    # profile
    "SkillItem",
    "ProjectItem",
    "ExperienceItem",
    "JDProfile",
    "ResumeProfile",
    # gap
    "GapItem",
    # gold
    "GoldItem",
    "QualityLevel",
    "LEVEL_TO_SCORE",
    # question
    "Question",
    "QuestionPlan",
    # decision
    "Decision",
    # score
    "Signals",
    "DimensionScore",
    "AnswerScore",
    # turn
    "Turn",
    # report
    "Strength",
    "Weakness",
    "Report",
    "ReportDraft",
    # api
    "SessionCreate",
    "SessionCreated",
    "AnswerIn",
    "TurnOut",
]



