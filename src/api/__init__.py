"""接口层：把 LangGraph 图包成 HTTP 服务。

分层原则（面试时被问到「后端怎么分层」能直接照这个讲）：**按调用关系切文件，不按层次切**。

    端点文件（routes/sessions/create.py 等）
        一个端点 = 一个文件；这个端点自己调用的私有函数（`_start_interview`、
        `_submit_answer`、`_save_report_if_finished`）就写在同一文件里。
        改一个接口只需要看一个文件，不用在 routes / service 之间来回跳。

    graph_io.py
        只放「被 2 个以上端点共用」的原语：推进图、读快照、构造响应、会话 id。
        共用代码集中在明确标注的文件里，而不是复制进每个端点。

    deps.py
        跨端点复用的前置条件：图单例、按 id 取会话、会话必须未结束（依赖注入）。

    errors.py
        错误的唯一出口：所有异常都变成同一种 JSON 形状。

**业务规则不放这里**——出题/评分/决策全在图里。放在接口层的规则不进 checkpointer，
也进不了 gold 集评测，等于"这段逻辑以后没人评得了它对不对"。
"""

from src.api.routes import api_router

__all__ = ["api_router"]
