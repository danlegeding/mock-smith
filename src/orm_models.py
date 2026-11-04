"""业务表（Tortoise ORM 模型）。

和 `src/model/` 的区别：
- `src/model/` 是 **Pydantic 模型**，管"进出的数据长什么样"（给 LLM、给 API 用）。
- 本文件是 **Tortoise 模型**，管"数据落在哪张表、什么列、什么外键"（给数据库用）。

两者是同一份信息的两面。别混用：Pydantic 不做 SQL，Tortoise 不做字段校验和 JSON 序列化。
报告落库时是 `Report.model_dump(mode="json")` → 塞进下面的 `ReportRecord`。
"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class SessionRecord(Model):
    """一次模拟面试 = 一行。

    坑：`session_id` 直接复用 LangGraph 的 `thread_id`，这样"续面"和"归档"找的是同一条记录。
    """

    session_id = fields.CharField(max_length=64, pk=True, description="同时是 LangGraph 的 thread_id")
    jd_title = fields.CharField(max_length=200, default="", description="岗位名，方便列表展示")
    status = fields.CharField(max_length=20, default="active", description="active / finished / abandoned")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "sessions"

    def __str__(self) -> str:
        return f"<SessionRecord {self.session_id}>"


class ReportRecord(Model):
    """最终报告 = 一行。

    为什么把结构化内容存 JSONB 而不是拆成更多表：
    报告会被整体读出来展示，很少按 single 的亮点/弱项去 SQL 过滤；
    而 `overall_score`、`turns_used` 这种要排序/统计的标量单独成列，能走索引。
    """

    id = fields.IntField(pk=True)
    session = fields.ForeignKeyField(
        "models.SessionRecord", related_name="reports", on_delete=fields.CASCADE
    )
    overall = fields.TextField(description="总体结论，一句话")
    overall_score = fields.FloatField(default=0.0, description="各维度均分的再平均，0-5")
    dimension_summary = fields.JSONField(default=dict, description="各维度均分 {dimension: score}")
    strengths = fields.JSONField(default=list, description="亮点列表")
    weaknesses = fields.JSONField(default=list, description="弱项列表")
    gap_conclusion = fields.TextField(default="", description="对照 JD 的缺口结论")
    next_steps = fields.JSONField(default=list, description="3 条可执行建议")
    turns_used = fields.IntField(default=0, description="实际用了几轮")
    skipped_dims = fields.JSONField(default=list, description="哪些维度没覆盖到")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "reports"

    def __str__(self) -> str:
        return f"<ReportRecord {self.id} session={self.session_id}>"
