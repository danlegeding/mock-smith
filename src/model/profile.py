"""输入侧：parse_inputs 节点把 JD / 简历原文解析成这些结构。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from .enums import Seniority


class SkillItem(BaseModel):
    """一项技能要求。id 是用来被问题引用的（Question.evidence_ref）。"""

    id: str = Field(description="稳定 id，如 s1、s2，用于被 Question.evidence_ref 引用")
    name: str = Field(min_length=1, description="技能名，如 Python / LangGraph / pgvector")
    weight: int = Field(ge=1, le=5, description="重要程度 1-5，5 最重要；JD 里'必须'给 4-5")


class ProjectItem(BaseModel):
    """简历里的一个项目。"""

    id: str = Field(description="稳定 id，如 p1、p2")
    name: str = Field(min_length=1, description="项目名，如'知识库问答 Agent'")
    tech_stack: list[str] = Field(default_factory=list, description="用到的技术，如 ['Python','pgvector']")
    my_role: str = Field(default="", description="候选人具体负责的部分，一句话")
    result: str = Field(default="", description="量化结果，如'召回率 0.62 -> 0.81'；没有就留空")


class ExperienceItem(BaseModel):
    """简历里的一段经历（实习/竞赛/开源）。"""

    id: str = Field(description="稳定 id，如 e1、e2")
    title: str = Field(min_length=1, description="经历标题，如'后端开发实习'")
    description: str = Field(default="", description="一两句话说明做了什么")


class JDProfile(BaseModel):
    """一份 JD 的结构化结果。"""

    role_title: str = Field(min_length=1, description="岗位名，如'AI Agent 开发实习生'")
    seniority: Seniority = Field(description="级别：intern 实习 / campus 校招 / social 社招")
    must_skills: list[SkillItem] = Field(min_length=1, description="硬性要求，对应 JD 里'必须/熟悉'")
    nice_skills: list[SkillItem] = Field(default_factory=list, description="加分项，对应 JD 里'加分/优先'")
    responsibilities: list[str] = Field(min_length=1, description="职责描述，是出情景题的素材库")
    domain_keywords: list[str] = Field(default_factory=list, description="业务领域词，用于生成情景题")


class ResumeProfile(BaseModel):
    """一份简历的结构化结果。"""

    projects: list[ProjectItem] = Field(min_length=1, description="项目列表，至少 1 个")
    skills: list[str] = Field(default_factory=list, description="候选人自己声明掌握的技能")
    experiences: list[ExperienceItem] = Field(default_factory=list, description="实习/竞赛/开源经历")
    education: str = Field(default="", description="学校/专业/年级，一行")
