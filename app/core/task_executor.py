"""任务执行器注册器 — 每种 TaskType 一个实现。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from contracts.models import Task, TaskType


class TaskExecutor(ABC):
    """任务执行器 — 每种 TaskType 一个实现。"""

    task_type: TaskType

    @abstractmethod
    async def run(self, task: Task) -> None:
        """执行任务逻辑。

        Args:
            task: 待执行的任务。
        """
        ...


class GenerateTaskExecutor(TaskExecutor):
    """PRD→TSD 生成任务执行器。"""

    task_type = TaskType.GENERATE

    async def run(self, task: Task) -> None:
        """执行生成任务。

        Args:
            task: 生成任务。
        """
        from app.orchestrator.main_graph import build_orchestrator_graph
        from app.orchestrator.state import make_initial_state

        orchestrator = build_orchestrator_graph()
        state = make_initial_state(
            task_id=task.id,
            workspace_id=task.workspace_id,
            user_id=task.user_id,
        )
        await orchestrator.ainvoke(state)


class ReindexTaskExecutor(TaskExecutor):
    """文档重索引任务执行器。"""

    task_type = TaskType.REINDEX

    async def run(self, task: Task) -> None:
        """执行重索引任务。

        Args:
            task: 重索引任务。
        """
        from app.knowledge_layer.pipeline import KnowledgeGraphBuilder

        builder = KnowledgeGraphBuilder()
        for doc_id in task.metadata.get("document_ids", []):
            await builder.build_from_document(doc_id)
            task.current_step += 1
            task.progress = task.current_step / task.total_steps


class EvaluateTaskExecutor(TaskExecutor):
    """方案评测任务执行器。"""

    task_type = TaskType.EVALUATE

    async def run(self, task: Task) -> None:
        """执行评测任务。

        Args:
            task: 评测任务。
        """
        # 委托到 evaluation layer
        from app.evaluation.agent_graph import EvaluationOrchestrator

        evaluator = EvaluationOrchestrator()
        result = await evaluator.evaluate(task.metadata.get("solution_id", ""))
        task.result = {"evaluation": result.model_dump() if hasattr(result, "model_dump") else result}


class WebSyncTaskExecutor(TaskExecutor):
    """Web 资源同步任务执行器。"""

    task_type = TaskType.WEB_SYNC

    async def run(self, task: Task) -> None:
        """执行 Web 同步任务。

        Args:
            task: Web 同步任务。
        """
        from app.web_indexing import WebIndexer

        indexer = WebIndexer()
        urls = task.metadata.get("urls", [])
        for url in urls:
            await indexer.index_url(url, task.workspace_id)
            task.current_step += 1
            task.progress = task.current_step / task.total_steps


class TaskExecutorRegistry:
    """任务执行器注册器。"""

    _executors: dict[TaskType, TaskExecutor] = {}

    @classmethod
    def register(cls, executor: TaskExecutor) -> None:
        """注册任务执行器。

        Args:
            executor: 任务执行器实例。
        """
        cls._executors[executor.task_type] = executor

    @classmethod
    def get(cls, task_type: TaskType) -> TaskExecutor:
        """获取任务执行器。

        Args:
            task_type: 任务类型。

        Returns:
            任务执行器实例。

        Raises:
            ValueError: 未注册的任务类型。
        """
        exe = cls._executors.get(task_type)
        if not exe:
            raise ValueError(f"未注册的任务执行器: {task_type}")
        return exe

    @classmethod
    def get_all_types(cls) -> list[TaskType]:
        """获取所有已注册的任务类型。"""
        return list(cls._executors.keys())


# 注册默认执行器
TaskExecutorRegistry.register(GenerateTaskExecutor())
TaskExecutorRegistry.register(ReindexTaskExecutor())
TaskExecutorRegistry.register(EvaluateTaskExecutor())
TaskExecutorRegistry.register(WebSyncTaskExecutor())
