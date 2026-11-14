"""进程池（ProcessPoolExecutor）在本项目里能干什么、不能干什么。

跑法：
    python scripts/demo_process_pool.py              # 串行 2 场 vs 进程池 2 场，对比耗时
    python scripts/demo_process_pool.py --jobs 3     # 3 场

先说结论（跑完能自己看到）：
1. **graph 对象不能丢进进程池**——里面有 psycopg 连接池、锁、线程，pickle 不了。
   所以不是「把 graph.invoke 换成 executor.submit(graph.invoke, ...)」这么改，
   而是**每个子进程自己建一份 graph + 自己建连接池**。
2. 进程池适合**离线批量任务**：一次跑 N 场面试、批量评测、压测。
   不适合放到 FastAPI 请求路径上：请求等的是 LLM 网络 IO（线程池就够），
   开进程反而要多付「每进程一份连接池 + 启动 import 时间」。
3. 子进程里必须自己 close_pool()，否则父进程退出时会被子进程的池线程拖住。
"""

from __future__ import annotations

import os
import pickle
import sys
import time
from argparse import ArgumentParser
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


def run_one(job: dict) -> dict:
    """子进程里跑一场：自己建图 → 问到第一题就停 → 关池返回。

    注意：这个函数必须是**模块级**函数（能被 pickle），里面不能捕获父进程的对象。
    ppid 和 pid 打出来是为了让你看见「真的在不同进程里跑的」。
    """
    from src.db import close_pool
    from src.graph.build import build_persistent_graph

    started = time.perf_counter()
    graph = build_persistent_graph()
    config = {"configurable": {"thread_id": job["thread_id"]}}
    try:
        graph.invoke(
            {
                "jd_text": Path(job["jd"]).read_text(encoding="utf-8"),
                "resume_text": Path(job["resume"]).read_text(encoding="utf-8"),
            },
            config=config,
        )
        snapshot = graph.get_state(config)
        question = None
        for task in snapshot.tasks:
            for item in task.interrupts:
                question = item.value
                break
        return {
            "thread": job["thread_id"],
            "pid": os.getpid(),
            "parent_pid": os.getppid(),
            "elapsed": round(time.perf_counter() - started, 1),
            "question": (question or {}).get("text", "(没拿到题目)"),
        }
    finally:
        close_pool()


def make_jobs(count: int, tag: str) -> list[dict]:
    jd = ROOT / "data" / "jds" / "01-ai-agent-intern.md"
    resume = ROOT / "data" / "resumes" / "sample-02-medium.md"
    stamp = int(time.time())
    return [
        {
            # 每次跑用新的 thread_id：已有 checkpoint 的会话会被当成"续跑"，
            # 演示里要的是每场都从头跑一遍，否则时间对比没有意义。
            "thread_id": f"pp-{tag}-{stamp}-{i}",
            "jd": str(jd),
            "resume": str(resume),
        }
        for i in range(1, count + 1)
    ]


def prove_not_picklable() -> None:
    """先让人亲眼看到：图对象塞不进进程池。"""
    from src.db import close_pool
    from src.graph.build import build_persistent_graph

    graph = build_persistent_graph()
    try:
        pickle.dumps(graph)
        print("[pickle] 居然成功了？那说明图里没有连接池，可以试试直接丢进进程池")
    except Exception as exc:  # noqa: BLE001 - 这里就是要展示失败原因
        print(f"[pickle] graph 不能跨进程传：{type(exc).__name__}: {exc}")
        print("          → 所以子进程只能自己 build_persistent_graph()")
    finally:
        close_pool()


def main() -> int:
    parser = ArgumentParser(description="进程池 vs 串行：批量跑面试的耗时对比")
    parser.add_argument("--jobs", type=int, default=2, help="跑几场（默认 2）")
    args = parser.parse_args()

    print("=" * 78)
    print(f"进程池演示：{args.jobs} 场面试（每场只跑到第一题就停，省时间省钱）")
    print("=" * 78)

    prove_not_picklable()
    print()

    jobs = make_jobs(args.jobs, "serial")
    print(f"--- 串行：一个一个跑（父进程 pid={os.getpid()}）---")
    serial_started = time.perf_counter()
    serial_results = [run_one(job) for job in jobs]
    serial_elapsed = round(time.perf_counter() - serial_started, 1)
    for result in serial_results:
        print(f"  pid={result['pid']:<6} {result['elapsed']:>5.1f}s  {result['thread']}  {result['question'][:30]}")
    print(f"  串行总耗时：{serial_elapsed}s")

    print()
    jobs = make_jobs(args.jobs, "pool")
    print(f"--- 进程池：{args.jobs} 个 worker 同时跑 ---")
    pool_started = time.perf_counter()
    with ProcessPoolExecutor(max_workers=args.jobs) as pool:
        pool_results = list(pool.map(run_one, jobs))
    pool_elapsed = round(time.perf_counter() - pool_started, 1)
    for result in pool_results:
        print(f"  pid={result['pid']:<6} {result['elapsed']:>5.1f}s  {result['thread']}  {result['question'][:30]}")
    print(f"  进程池总耗时：{pool_elapsed}s")

    print()
    print("=" * 78)
    speedup = serial_elapsed / pool_elapsed if pool_elapsed else 0
    print(f"串行 {serial_elapsed}s → 进程池 {pool_elapsed}s（快 {speedup:.2f} 倍）")
    print("注意：并行收益来自「等 LLM 的时间重叠」，不是 CPU 变快；")
    print("      每场约 20~30s 里 90% 是在等模型返回。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
