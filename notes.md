# 已知问题 / 待办笔记

> 用途：prompt 抽得不完美的地方先记下来，等 gold 集（D7 之后）建好再量化修。
> 不要在没指标的情况下反复调 prompt —— 单次目测分不清"真变好"和"随机波动"。

## P1 · JD 解析的已知缺陷

换了默认模型之后（gpt-4o-mini → gpt-5.4-mini），同一份 JD 的结果明显变好，逐条对一下：

| # | 现象 | 属于哪类 | 现在的状态（2026-10-26，gpt-5.4-mini） |
|---|---|---|---|
| 1 | "LangChain / LangGraph" 只抽出 LangGraph，LangChain 连漏 3 轮 | 漏抽（并列技术） | **已改善**：两个都抽到了 |
| 2 | "有 RAG 项目经验……优先" 的 RAG 被放进 `must_skills` | 分桶错（优先 → nice） | **仍存在**：RAG 在 `must_skills` 里（weight 4） |
| 3 | `weight` 全部给 3，没有区分"职责核心"和"一句带过" | 权重校准 | **已改善**：出现 4/3/2 的区分 |
| 4 | `nice_skills` 基本为空 | 漏抽（加分项） | **已改善**：抽出 5 条（pgvector / LLM Evaluation / Open Source Contributions…） |

结论：**"模型能力"和"prompt 写法"是两个变量**。之前那版 prompt 在 gpt-4o-mini 上看着像 prompt 问题，
换成 gpt-5.4-mini 就少了一半。所以调 prompt 之前先确认模型本身没拖后腿——这也是为什么要有 gold 集：
换模型是一次性的大变量，prompt 是细调，两者的收益必须能分开量。

## P2 · 非确定性观察（重要，面试可讲）

同一个 prompt、`temperature=0`，连跑两次结果不同：
- 一次 `nice_skills` = [AI 应用项目, LLM 评测方法, 开源贡献]
- 另一次 `nice_skills` = [pgvector, LLM]

结论：**不能用"跑一次看起来对"当作验收**。这也是为什么要 gold 集 + 指标，而不是靠肉眼调 prompt。

## P3 · 环境/工程

- **`pip install tortoise` 和 `tortoise-orm` 是两个完全不同的包。**
  2026-10-26 19:48 装了 `tortoise==0.1.1`（一个海龟绘图库），它的 import 名也是 `tortoise`，
  直接把 `tortoise-orm` 的包目录**覆盖**了，症状是 `AttributeError: type object 'Tortoise' has no attribute 'init'`
  （Tortoise 变成了海龟对象，方法里有 forward/left/right/setAutoDraw）。
  修法：`pip uninstall -y tortoise` → `pip install --force-reinstall --no-deps tortoise-orm==1.1.9`。
  教训：装包前确认「发行包名 ≠ import 名」这件事，装完跑一次 `import` 自检。
- `src/llm.py` 的配置从 `os.getenv` 读（`load_dotenv()` 在模块顶部调一次，不带 `override=True`）；
  `src/config.py` 只管数据库。两边各管一摊，别在两个地方都留一份默认值。
- `.env` 的键名是 `CLOSEAI_API_KEY` / `CLOSEAI_API_URL`；`llm.py` 里 `_env()` 会依次尝试
  `CLOSEAI_* / OPENAI_* / LLM_*`，改 `.env` 换名字不用改代码。
- `gpt-5.4-mini` 不接受 `max_tokens`（要用 `max_completion_tokens`）；直接调 openai SDK 会踩，
  走 langchain 的 `ChatOpenAI` 不会。`temperature=0` 在它上面可用。
- `POSTGRES_PASSWORD` 只在数据库空卷首次创建时生效；改密码必须 `docker compose down -v`。
- `DATABASE_URL` 里的密码含 `@` 时必须写成 `%40`。

## P4 · 设计决策：为什么 `match_gap` 用代码判档，而不是交给 LLM

**讨论起点**：strong/weak/missing 本质是语义匹配，`match_gap.py` 里一半代码在模拟语义
（别名表、技能名归一化、原文回找），看起来像"该给模型干的活"。这个质疑是对的。

**为什么仍然用代码**（三条代价，按硬度排）：

1. **证据必须逐字原文**：代码版能从简历里切出原文片段作为 `evidence_quote`；LLM 会转述。
   下游 `Question.evidence_ref`、报告引文核对、gold 标注全依赖逐字引用。
   （已有教训：模型把 `MySQL基础` 写成 `MySQL`，见 P1/b17。）
2. **可复现性**：判档结果决定出题策略，进而决定整场面试走向。代码是纯函数，
   `check_gap.py` 15 条断言稳定；LLM 即使 `temperature=0` 也会抖，测试变 flaky（见 P2）。
3. **成本与延迟**：`match_gap` 每场跑一次。代码 ~0ms；LLM 一次 1–3s + token + 重试。

**如果以后要改成 LLM，正确姿势是分工而不是替换**：

```
LLM  ：只输出 [(skill, level)]          ← 判档交给模型
代码 ：① skill 必须在 JD 列表里
       ② 按 level 到简历原文回找逐字证据（找不到就降级 / 记无效）
```

这与 `evaluate_answer` 的做法一致：模型给判断，`verify_quote` 逐字核对，
`_keep_quoted` 丢弃编造条目。**语义判断归模型，可验证性归代码。**

**已知代价**：别名表（`_lookup_related_terms`）靠手工维护，新 JD 出现新叫法时会漏判。
更省事的折中是「离线用 LLM 生成别名表 → 落成静态数据 → 运行时仍走代码」，
确定性与语义能力兼得，只牺牲新技能的时效。
