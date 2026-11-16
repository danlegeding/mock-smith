"""业务表（Tortoise ORM 模型）。"""

from __future__ import annotations

from tortoise import fields
from tortoise.models import Model


class SessionRecord(Model):
    """一次模拟面试 = 一行。"""

    session_id = fields.CharField(max_length=64, pk=True, description="同时是 LangGraph 的 thread_id")
    jd_title = fields.CharField(max_length=200, default="", description="岗位名，方便列表展示")
    status = fields.CharField(max_length=20, default="active", description="active / finished / abandoned")
    created_at = fields.DatetimeField(auto_now_add=True)

    class Meta:
        table = "sessions"

    def __str__(self) -> str:
        return f"<SessionRecord {self.session_id}>"


class ReportRecord(Model):
    """最终报告 = 一行。"""

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
