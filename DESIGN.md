# 模拟面试 Agent — 设计规格 v0.1

> 用途：大二寒假实习求职项目，手写实现。
> 本文只给**契约与决策**，不给实现代码。每个函数体由你自己写。
> 读完本文你应该能：白板画出状态机、说清每条护栏为什么存在、说清每个指标怎么算。

---

## 0. 项目定位

**做什么**：用户上传一份 JD + 一份简历 → Agent 解析出岗位要求与候选人画像 → 找出匹配与缺口 → 围绕缺口和 JD 核心技能出题 → **根据用户回答动态追问**（答得好加难度、答得空降级或换角度）→ 结束后产出结构化报告（分维度评分 + 引用原话的亮点/问题 + 下一步建议）。

**不做什么**（写进 README 的"范围外"，这本身就是工程素养）：
- 不做通用聊天；每一轮都必须服务于"采集能力证据"
- 不做题库检索式出题（那是 RAG 问答，不是 Agent）
- 不做简历改写（那是另一个产品）
- 不做语音（ASR/TTS 会吃掉全部时间预算）

**核心卖点（面试时的一句话）**：
> 把主观的面试评估做成了可量化的：先用 rubric + 证据引用约束评分，再用 20 份人工标注的 gold 回答校准，report Spearman 相关系数。不靠"感觉很准"。

---

## 0.5 MVP 裁剪范围（2026-10-26 定，与下文冲突时**以本节为准**）

动机：这个项目要的是"能跑、能演示、能讲清"，不是上生产。**只处理正常路径**，不为极端情况写兜底。

### 保留（核心，别动）

- 9 节点状态机：`parse_inputs → match_gap → plan_questions → select_question → ask → evaluate_answer → decide_next → generate_followup / generate_report`
- Postgres checkpointer 断点续跑（D1 已过验收）
- 5 维度 rubric + 评分强制 `evidence_quote`
- `decide_next` 规则（policy 可单测，这是差异化所在）
- LLM 输出的 JSON 校验失败重试（最多 3 次）——**这是常态不是异常**，已实现，但不再加码
- 终端交互 `scripts/play.py`（演示载体）

### 砍掉 / 收紧

| 原计划 | MVP 处理 |
|---|---|
| 13 条护栏（§4） | 只留 4 条：G1 问题必须锚定 JD/简历、G5 追问必引上一轮原话、G6 评分必带证据、G8 不问年龄婚育等隐私 |
| 7 个评测指标（§7.1） | 只算 2 个：M1 评分一致性（Spearman）、M2 追问引用率 |
| gold 20 份 + 双人标注 + kappa（§7.2） | 10 份、单人标注，不算 kappa |
| 消融 A–E（§7.3） | 换成 1 个粗对比：同一简历跑 2 个 session，「有 decide_next 规则」vs「让模型自选下一问」 |
| 对话轮数预算 12 | 6 |
| 数据规模 3 JD × 3 简历 | 主用 1 份 JD + 3 份简历 |
| FastAPI SSE 流式（§5） | 砍。只留 3 个同步接口：`POST /sessions`、`POST /sessions/{id}/answer`、`GET /sessions/{id}/report` |
| 把 FastAPI 也容器化 | 砍。compose 里只留数据库，API 本地跑 |
| 每轮全评 5 个维度 | 每轮只评「当前题所属维度 + 1 个辅助维度」，报告时按维度聚合 |
| 相似度判重 / token 上限 / 引用可溯源率 | 砍 |

### 明确不做

多用户并发、鉴权、多语言界面、语音输入输出、简历改写。

---

## 1. 关键设计决策（每条都要能讲出 why）

| 决策 | 选择 | 为什么 |
|---|---|---|
| 为什么是 Agent 不是一次性生成题单 | 每轮回答后**重新决策**下一步 | 追问条件依赖上一轮内容；一次性生成无法做到"答得好就加难度" |
| 编排框架 | LangGraph 状态机 | 需要显式状态（进度/覆盖/难度）+ 条件边（policy 可测）+ checkpoint（断线续面）+ interrupt（HITL） |
| 状态存储 | Postgres checkpointer | 面试可能 20 分钟，服务重启要能续；同时体现你会用持久化状态而不是内存 dict |
| 业务表存储 | **Tortoise ORM**（asyncpg，异步） | checkpointer 存的是 JSONB blob，能续跑但不能聚合（"按维度均分排序"没法在 blob 上做）；业务表要外键、要索引、要能改结构，所以单独用 ORM 声明 |
| 上下文策略 | **只喂结构化 profile + 最近 3 轮**，不喂全文 | 简历+JD 全文每轮重发会爆 token；且模型会"记住太多"导致跑题 |
| 评分方式 | LLM-as-judge + 结构化输出 + **强制证据引用** | 无证据的分数不可信；有引用才能被人工抽查 |
| 评分校准 | 人工标注 gold 集 + Spearman | 这是本项目唯一能拿出的硬指标，也是差异化所在 |
| 生成温度 | 出题用 0.7，评分用 0（必要时多次取中位） | 出题要多样性，评分要稳定 |

### 1.1 两条存储通道（别混）

同一个 Postgres 库里有两套表，各由一套代码管：

| 通道 | 代码 | 表 | 谁建表 |
|---|---|---|---|
| 图的状态 | `src/db.py`（psycopg 同步连接池） | `checkpoints` / `checkpoint_blobs` / `checkpoint_writes` | LangGraph 的 `PostgresSaver.setup()` |
| 业务数据 | `src/orm.py` + `src/orm_models.py`（Tortoise ORM + asyncpg，异步） | `sessions` / `reports` | 我们的 `Tortoise.generate_schemas(safe=True)` |

规则：
- 图的状态**只**走 checkpointer，不要自己再往 `sessions`/`reports` 抄一份 state（两份真相必不一致）。
- 报告只在结束时写一次：`Report.model_dump(mode="json")` → `ReportRecord`。
- Pydantic 模型（`src/model/`）管"数据长什么样"，Tortoise 模型（`src/orm_models.py`）管"落在哪张表"。两者都别越界。

---

## 2. 领域模型（Pydantic，字段契约）

> 你要写的 `src/model/`（数据契约包，按用途拆成 8 个文件）。字段名照抄，类型自己定细节。

### `JDProfile`
| 字段 | 类型 | 说明 |
|---|---|---|
| `role_title` | str | 岗位名，如"AI Agent 开发实习生" |
| `seniority` | enum(实习/校招/社招) | 级别，影响出题难度基线 |
| `must_skills` | list[SkillItem] | 硬性要求（JD 里"必须/熟悉"） |
| `nice_skills` | list[SkillItem] | 加分项 |
| `responsibilities` | list[str] | 职责描述，出题的场景来源 |
| `domain_keywords` | list[str] | 业务领域词，用于生成情景题 |

### `ResumeProfile`
| 字段 | 类型 | 说明 |
|---|---|---|
| `projects` | list[ProjectItem] | 项目名 + 技术栈 + 你负责的部分 + 量化结果 |
| `skills` | list[str] | 声明掌握的技能 |
| `experiences` | list[ExperienceItem] | 实习/竞赛/开源 |
| `education` | str | 学校/专业/年级 |

### `GapItem`
| 字段 | 说明 |
|---|---|
| `skill` | 对应 JD 的哪一项 |
| `match_level` | enum: strong / weak / missing |
| `evidence` | 简历原文片段（必须是原文子串，否则后期算幻觉） |
| `priority` | 1-5，越高越该问 |
| `probe_angle` | 建议的考察角度（如"让他讲一致性方案"） |

### `Question`
| 字段 | 说明 |
|---|---|
| `text` | 问题文本，≤60 字 |
| `dimension` | 考察维度（见 §6 维度表） |
| `difficulty` | 1 / 2 / 3 |
| `evidence_ref` | **必填**：问题依据的 JD 技能或简历条目 id |
| `anchor_quote` | 追问时必填：上轮回答中被追问的原话片段 |
| `kind` | enum: opening / followup / scenario（"深挖"由决策层 `DecideAction.DEEPEN` 表达，不是题的类型） |

### `AnswerScore`
| 字段 | 说明 |
|---|---|
| `dimension_scores` | dict[维度 → {score: 1-5, evidence_quote: str, comment: str}] |
| `valid` | bool，任一维度无 evidence_quote 则该维度记 invalid |
| `signals` | {too_short, off_topic, has_concrete_example, has_numbers}，供 policy 用 |

### `Report`
| 字段 | 说明 |
|---|---|
| `overall` | 总体结论 + 是否建议推进（一句话） |
| `dimension_summary` | 各维度均分 |
| `strengths` | list[{point, evidence_quote}] ← 必须引用候选人原话 |
| `weaknesses` | list[{point, evidence_quote, suggestion}] |
| `gap_conclusion` | 对照 JD 的缺口结论 |
| `next_steps` | 3 条可执行建议 |

---

## 3. LangGraph 状态机

### 节点

| # | 节点 | 职责 | 输入 | 输出 |
|---|---|---|---|---|
| 1 | `parse_inputs` | 把 JD/简历原文转结构化 profile | jd_text, resume_text | jd_profile, resume_profile |
| 2 | `match_gap` | 逐技能比对，产出缺口表 | 两个 profile | gap_map |
| 3 | `plan_questions` | 生成带维度/难度的题池（不直接问） | gap_map, jd_profile | question_plan |
| 4 | `select_question` | policy：从题池挑下一个（考虑覆盖度、优先级、难度） | state | current_question |
| 5 | `ask` | 输出问题，**interrupt 等用户回答** | current_question | answer, turns+1 |
| 6 | `evaluate_answer` | 单答评分 + 生成 signals | answer, current_question | 评分、signals |
| 7 | `decide_next` | **核心 policy**：深挖/换维度/升降难度/结束 | 评分, coverage, 轮数 | action |
| 8 | `generate_followup` | 基于上轮回答生成追问（必须引用原话） | 上一答, action | Question(kind=followup) |
| 9 | `generate_report` | 汇总出报告 | turns, 评分 | report |

### 条件边

```
START
  → parse_inputs
  → match_gap
  → plan_questions
  → select_question
  → ask ──(用户答)──→ evaluate_answer
  → decide_next
       ├─ deepen   → generate_followup ──→ ask
       ├─ switch_dim / raise / lower → select_question ──→ ask
       └─ end → generate_report → END
```

**`decide_next` 的判定顺序（写死，别让模型自由发挥）**：

1. 轮数 ≥ `turn_budget`(12) 或 token 超限 → `end`
2. 用户主动 `/end` 或 `skip` 超过 3 次 → `end`
3. 上一答被判定 `off_topic` 或 `too_short` → `lower_difficulty`（同一维度换角度重问，不换维度）
4. 上一答 `has_concrete_example` 且 `has_numbers` 且评分 ≥4 → `deepen`（或 `raise_difficulty`）
5. 当前维度覆盖次数 < 2 且优先级 ≥4 → `deepen`
6. 其他 → `switch_dim`（选覆盖次数最少且未结束的维度）

**设计要点**：`decide_next` 先跑**规则**，规则不确定时才让 LLM 兜底。这样 policy 可单测、可解释——面试时这句话很值钱。

### State 字段

| 字段 | 说明 |
|---|---|
| `jd_text` / `resume_text` | 原始输入，**只在 parse 和证据检索时用**，不要每轮进 prompt |
| `jd_profile` / `resume_profile` / `gap_map` | 解析产物，常驻 |
| `question_plan` | 题池，可运行时追加 |
| `current_question` | 当前待答问题 |
| `answer` | 当前回答 |
| `turns` | list[Turn]，每条含 question / answer / score |
| `coverage` | dict[维度 → 已问次数] |
| `difficulty` | 当前难度 1-3 |
| `turn_budget` | 默认 12 |
| `token_usage` | 累计，用于成本护栏 |
| `skip_count` | 用户跳过次数 |
| `report` | 最终产物 |

---

## 4. 护栏规则清单（`guards.py`，13 条）

> 每条都是纯函数：输入候选对象，输出 `(ok: bool, reason: str)`。
> 被拦截时**重生成 ≤2 次**，仍失败则丢弃该候选并换池里下一个。

| # | 规则 | 检测方式 | 违反时 |
|---|---|---|---|
| G1 | 问题必须锚定 JD 技能或简历条目 | `evidence_ref` 非空且能在 profile 里找到 | 重生成 |
| G2 | 不得引用简历中不存在的项目/公司名 | 抽专有名词，比对 profile | 直接丢弃 |
| G3 | 单轮只问一个问题 | 问号 ≤1，且不含"并且/同时/还有"连接的并列疑问 | 截断取第一问 |
| G4 | 不得泄露答案或评分标准 | 关键词黑名单 + 轻量自检 | 重生成 |
| G5 | 追问必须引用上轮回答原话 | `anchor_quote` 规范化后必须是上轮 answer 的子串 | 重生成 |
| G6 | 评分必须有证据引用 | 每个维度分都要 `evidence_quote` 非空 | 该维度置 invalid |
| G7 | 报告不得编造候选人经历 | 报告里所有引用必须能在 `turns` 里检索到 | 删除该条，记一次 hallucination |
| G8 | 合规：不问年龄/婚育/籍贯/政治/宗教/健康 | 关键词表 + 兜底分类 | 丢弃换题 |
| G9 | 难度只能在 {1,2,3} | 枚举校验 | 钳位 |
| G10 | 轮数上限 | 计数器 | 强制 `generate_report` |
| G11 | 问题 ≤60 字，追问 ≤40 字 | 字符数 | 裁剪或重生成 |
| G12 | 不得语义重复 | 与历史问题 embedding 余弦 > 0.9 即判重 | 丢弃换题 |
| G13 | token / 成本上限 | 累计 usage | 强制出报告 |

**G7 是重点**：报告里"候选人提到用 Redis 做缓存"必须是真的说过。写个 `verify_citations(report, turns)` 自动核查，把"引用可溯源率"作为评测指标之一。

---

## 5. API 契约（FastAPI）

| 方法 | 路径 | 入参 | 出参 |
|---|---|---|---|
| POST | `/sessions` | jd_text, resume_text | session_id, first_question, gap_summary |
| POST | `/sessions/{id}/answer` | answer | next_question, turn_no, action, score_preview(可选) |
| POST | `/sessions/{id}/skip` | — | next_question |
| POST | `/sessions/{id}/end` | — | report |
| GET | `/sessions/{id}/report` | — | report |
| GET | `/sessions/{id}/stream` | — | SSE，逐 token 推送问题 |

要点：`session_id` 同时是 LangGraph 的 `thread_id`；SSE 用 `text/event-stream`，前端 Streamlit 用 `st.write_stream`。

---

## 6. 考察维度表（评分 rubric 的骨架）

| 维度 | 看什么 | 1 分 | 3 分 | 5 分 |
|---|---|---|---|---|
| 技术深度 | 原理讲到多深 | 只报名词 | 讲清用法 | 讲清权衡与边界 |
| 项目真实性 | 是否真做过 | 全是"我们" | 能说自己的部分 | 有坑、有数字、有取舍 |
| 工程思维 | 有没有考虑失败 | 只讲顺利路径 | 提到测试/部署 | 主动谈失败与监控 |
| 沟通表达 | 结构是否清晰 | 散乱 | 有条理 | 先结论后论据 |
| 岗位匹配 | 是否贴合 JD | 泛泛而谈 | 覆盖核心要求 | 有对应场景经验 |

**注意**：维度必须"行为锚定"（如上），不能只写"技术深度好"。否则 LLM 打分每次漂移。

---

## 7. 评测口径（本项目最重要的部分）

### 7.1 指标定义

| 指标 | 定义 | 采集方式 | 目标 |
|---|---|---|---|
| **M1 评分一致性** | 你的 judge 分 vs 人工 gold 分的 Spearman ρ（总分）+ MAE | 20 份 gold 回答 | ρ ≥ 0.7 |
| **M2 追问引用率** | `anchor_quote` 确为上轮回答子串的比例 | 自动，100 轮跑批 | ≥ 95% |
| **M3 问题相关率** | 问题能被 `evidence_ref` 支撑的比例 | 自动 + 人工抽检 30 条 | ≥ 0.9 |
| **M4 重复率** | 与历史问题相似度 >0.9 的占比 | 自动 | ≤ 5% |
| **M5 引用可溯源率** | 报告引用能在对话里找到的比例（G7） | 自动 | 100% |
| **M6 覆盖均衡度** | 各维度覆盖次数的归一化熵 | 自动 | ≥ 0.8 |
| **M7 成本/时延** | 每场平均 token、平均轮数、P95 单轮延迟 | 打点 | 记录基线 |

### 7.2 gold 集怎么造（别偷懒，这是硬指标来源）

1. 准备 10 个固定问题 × 2 个质量档（好 / 差）= 20 份回答。来源：你自己 + 2 个同学真实作答，别用 LLM 生成后直接当 gold。
2. **2 人独立标注**每个维度 1-5 分，算 **Cohen's kappa**（目标 ≥0.6，低于就修订 rubric）。
3. 分歧项协商定稿，固化为 `eval/gold/gold.jsonl`，之后所有改动都在这上面跑。
4. **切分**：12 份 dev（可以看、可以调 prompt）+ 8 份 test（**只在最后跑**，防止过拟合）。这一条写进 README，面试官会认。

### 7.3 消融表模板（跑完填数，贴 README）

| 配置 | M1 ρ | M1 MAE | M2 引用率 | M3 相关率 | M4 重复率 | M6 均衡度 | 平均轮数 |
|---|---|---|---|---|---|---|---|
| A. baseline：一次性出 10 题，不追问，直接打分 | | | — | | — | — | 0 |
| B. + 追问循环（基于上轮回答） | | | | | | | |
| C. + 难度自适应（规则 policy） | | | | | | | |
| D. + 分维度 rubric（行为锚定） | | | | | | | |
| E. + 证据强制（G6/G7）＝最终版 | | | | | | | |

**预期结论**（写进 README 的分析段）：
- C 提升 M6 均衡度但可能降低 M1（难度跳太快评分失真）
- D 是 M1 提升最大的一步（从"打分"变成"按锚点打分"）
- E 让 M5 从 ~70% 到 100%，M1 也升（评委被迫找证据）

---

## 8. 目录结构

```
mock-interview-agent/
├── DESIGN.md                  # 本文件
├── README.md                  # 架构图 + 消融表 + demo
├── requirements.txt
├── .env.example
├── docker-compose.yml         # postgres(pgvector) + api
├── Dockerfile
├── docker/init.sql
├── src/
│   ├── config.py
│   ├── db.py                  # psycopg 连接池 + LangGraph checkpointer（图的状态）
│   ├── orm.py                 # Tortoise 初始化（asyncpg，业务表）
│   ├── orm_models.py          # Tortoise 表模型：sessions / reports
│   ├── llm.py                 # 模型工厂 + 重试 + 结构化输出封装
│   ├── model/                 # §2 的 Pydantic 模型（enums/profile/gap/question/score/turn/report/api + __init__ 统一导出）
│   ├── graph/
│   │   ├── state.py           # §3 的 State
│   │   ├── build.py           # 编译图 + 条件边
│   │   ├── guards.py          # §4 的 13 条护栏
│   │   ├── prompts/           # 每节点一个 .md 或 .py
│   │   └── nodes/             # 9 个节点，一文件一节点
│   ├── api/
│   │   ├── main.py
│   │   └── routes.py
│   └── eval/
│       ├── gold/gold.jsonl
│       ├── run_eval.py
│       ├── metrics.py
│       └── results.md
├── web/app.py                 # Streamlit 单文件
└── data/
    ├── jds/                   # 3-5 份真实 JD
    └── resumes/               # 你的 + 2 份同学简历（脱敏）
```

---

## 9. 第一周日程（验收标准写死）

| 天 | 任务 | 验收标准（做不到就不往下走） |
|---|---|---|
| D1 | 环境：docker-compose 起 PG(pgvector)、venv、依赖、`.env` | `docker compose up` 后能连库，`SELECT 1` 通过 |
| D2 | `src/model/` 全部模型（已拆包）+ 3 份 JD + 3 份简历样本进 `data/` | 能用 Pydantic 校验一份手写的假 JSON |
| D3 | `parse_inputs` 节点 | 喂一份 JD+简历，输出两个 profile，字段非空且合理 |
| D4 | `match_gap` 节点 | 输出 gap_map，`evidence` 字段确实是简历原文子串 |
| D5 | `plan_questions` 节点 | 产出 ≥10 题池，每题有 dimension/difficulty/evidence_ref |
| D6 | `build.py` 拼最小图：parse→match→plan→select→ask | 能跑出第 1 个问题（命令行即可） |
| D7 | 加 `ask` 的 interrupt + 命令行 3 轮问答（不做评分） | 能连着问 3 个问题，每题都能答，state 里 turns 正确累积 |

**第一周绝对不做**：评分、报告、前端、API、评测。**先把"能出题、能问 3 轮"跑通。**

---

## 10. 已知坑与对策

| 坑 | 现象 | 对策 |
|---|---|---|
| 评分漂移 | 同一份回答两次打分差 1 分 | 评分温度 0 + 行为锚定 rubric + 证据强制 + 3 次取中位数 |
| 追问变复读 | 追问和原问题一个意思 | G12 相似度过滤 + prompt 强制"引用上轮具体名词" |
| 长文本爆 token | 简历/JD 每轮重发 | 只发结构化 profile，原文只在 parse 阶段用 |
| 模型乱记上下文 | 后期忘了前面问过什么 | 覆盖度和已问列表存在 state，**由代码判断**，不靠模型记 |
| 问题越问越虚 | 脱离 JD | G1/G2 硬拦截，宁可换题也不发出去 |
| 评测过拟合 | dev 分数很好、test 崩 | 提前切 8 份 test，只在最后跑一次 |

---

## 11. 面试考点映射（准备被问这些）

| 面试官会问 | 你的答案锚点 |
|---|---|
| 为什么用 LangGraph 不用 while 循环 | 显式 state + 条件边可单测 + checkpointer 断线续面 + interrupt 做 HITL |
| 追问策略怎么设计 | `decide_next` 先规则后 LLM，6 条判定顺序写死，可单测 |
| 主观任务怎么评测 | rubric 行为锚定 + evidence 强制 + 20 份人工 gold + Spearman + kappa |
| 怎么防幻觉 | G1/G2/G7 三道拦截 + 引用可溯源率指标 |
| 多轮怎么管上下文 | 只喂结构化 profile + 最近 3 轮，覆盖度进 state |
| 成本怎么控 | G10/G13 + 只发 profile + 题池预生成 |
| 最难的地方 | 评分校准那两周：kappa 从 0.4 调到 0.65 的过程 |

---

## 12. 现在要做的第一件事

打开 D1 的清单，先把 `docker-compose.yml` 写出来（~30 行，全手写，不用 AI）。
写完后对照 §9 的验收标准逐条勾。
