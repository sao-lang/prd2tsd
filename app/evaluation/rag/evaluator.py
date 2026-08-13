"""RAG 评测器 — 检索质量（L1）+ 回答质量（L2），基于 ragas。"""

from __future__ import annotations

from typing import Any

from app.core.config import settings
from app.core.logger import get_logger
from app.evaluation.rag._compat import install_ragas_shims
from app.evaluation.rag.models import (
    RagEvalReport,
    RagEvalSummary,
    RagQueryScore,
    RagSample,
)
from app.knowledge_layer.pipeline import RetrievalPipeline
from app.llm_gateway import gateway

logger = get_logger("prd2tsd.eval.rag")

# 导入 ragas 前安装 langchain-community vertexai 兼容 shim
install_ragas_shims()
from ragas import EvaluationDataset, SingleTurnSample, evaluate  # noqa: E402
from ragas.metrics.collections import (  # noqa: E402
    answer_relevancy,
    context_precision,
    context_recall,
    faithfulness,
)


class RagEvaluator:
    """RAG 评测器。

    流程：对每个样本执行「检索 + LLM 回答」→ 组装 ragas 数据集 →
    计算 L1（context_precision / context_recall）+ L2（faithfulness / answer_relevancy）。

    Usage:
        evaluator = RagEvaluator()
        report = await evaluator.evaluate(samples, config={"top_k": 5})
    """

    def __init__(self, pipeline: RetrievalPipeline | None = None) -> None:
        """初始化评测器。

        Args:
            pipeline: RetrievalPipeline 实例（未提供时自动创建）。
        """
        self._pipeline = pipeline or RetrievalPipeline()

    def _apply_config(self, config: dict[str, Any] | None) -> None:
        """应用评测配置到管线。

        Args:
            config: 评测配置（mode/top_k/reflection/workspace_id）。
        """
        cfg = config or {}
        # 反思开关：reflection=false 时关闭反思循环
        if "reflection" in cfg:
            self._pipeline.max_reflection_rounds = 2 if cfg["reflection"] else 0

    def _build_answer_prompt(self, sample: RagSample, contexts: list[str]) -> str:
        """构建回答 Prompt（严格基于上下文，利于 faithfulness）。

        Args:
            sample: RAG 样本。
            contexts: 检索到的上下文列表。

        Returns:
            回答 Prompt 文本。
        """
        context_text = "\n".join(contexts) if contexts else "（无检索结果）"
        return (
            "请严格基于以下知识上下文回答用户问题。"
            "如果上下文中没有相关信息，请明确说明'上下文未包含相关信息'。\n\n"
            f"上下文：\n{context_text}\n\n问题：{sample.query}"
        )

    async def retrieve_and_answer(
        self,
        sample: RagSample,
        config: dict[str, Any] | None = None,
    ) -> tuple[Any, str, int]:
        """对单个样本执行检索 + 回答。

        Args:
            sample: RAG 样本。
            config: 检索配置。

        Returns:
            (RetrievalContext, 回答文本, 反思轮数占位)。
        """
        self._apply_config(config)
        cfg = config or {}
        ctx = await self._pipeline.retrieve(
            query=sample.query,
            mode=cfg.get("mode", sample.expected_mode or "hybrid"),
            top_k=cfg.get("top_k", 5),
            workspace_id=cfg.get("workspace_id", ""),
        )
        contexts = [doc.text for doc in ctx.results]
        prompt = self._build_answer_prompt(sample, contexts)
        resp = await gateway.complete(
            prompt=prompt,
            task_type="knowledge_qa",
            layer="evaluation",
            node="rag_evaluator",
            temperature=0.2,
            max_tokens=512,
        )
        # 反思轮数：pipeline 当前未暴露具体轮数，取最大轮数配置作为占位
        reflection_rounds = self._pipeline.max_reflection_rounds
        return ctx, resp.content, reflection_rounds

    def to_ragas_dataset(
        self,
        samples: list[RagSample],
        contexts: list[list[str]],
        answers: list[str],
    ) -> EvaluationDataset:
        """组装 ragas 评测数据集。

        Args:
            samples: RAG 样本。
            contexts: 每个样本的检索上下文列表。
            answers: 每个样本的 LLM 回答。

        Returns:
            ragas EvaluationDataset。
        """
        ragas_samples = [
            SingleTurnSample(
                user_input=sample.query,
                retrieved_contexts=ctxs,
                response=answer,
                reference=sample.reference_answer,
            )
            for sample, ctxs, answer in zip(samples, contexts, answers, strict=False)
        ]
        return EvaluationDataset(samples=ragas_samples)

    def _build_ragas_llm(self) -> Any | None:
        """构建 ragas 内部 judge LLM（复用项目 judge 配置）。

        Returns:
            ChatOpenAI 实例；未配置 API key 时返回 None（由 ragas 默认）。
        """
        cfg = settings.get_model_config_env("judge", "openai")
        if not cfg.get("api_key"):
            logger.warning("未配置 judge API key，ragas 将使用默认 LLM")
            return None
        from langchain_openai import ChatOpenAI

        return ChatOpenAI(
            model=cfg.get("default_model", "gpt-4o-mini"),
            api_key=cfg["api_key"],
            base_url=cfg.get("base_url") or None,
            temperature=0,
        )

    def _build_ragas_embeddings(self) -> Any | None:
        """构建 ragas 内部 embedding（复用项目 embedding 配置）。

        Returns:
            OpenAIEmbeddings 实例；未配置 API key 时返回 None。
        """
        cfg = settings.get_model_config_env("embedding", "openai")
        if not cfg.get("api_key"):
            return None
        from langchain_openai import OpenAIEmbeddings

        return OpenAIEmbeddings(
            model=cfg.get("default_model", "text-embedding-3-small"),
            api_key=cfg["api_key"],
            base_url=cfg.get("base_url") or None,
        )

    def evaluate(
        self,
        samples: list[RagSample],
        contexts: list[list[str]],
        answers: list[str],
        config: dict[str, Any] | None = None,
        llm: Any | None = None,
        embeddings: Any | None = None,
        dataset_version: str = "1.0",
        tokens: list[int] | None = None,
    ) -> RagEvalReport:
        """执行 RAG 评测（同步包装 ragas evaluate）。

        Args:
            samples: RAG 样本列表。
            contexts: 每个样本的检索上下文。
            answers: 每个样本的 LLM 回答。
            config: 检索配置（记录到报告）。
            llm: ragas judge LLM（默认从项目配置构建）。
            embeddings: ragas embedding（默认从项目配置构建）。
            dataset_version: 数据集版本。
            tokens: 每个样本的检索 token 数（默认全 0）。

        Returns:
            RagEvalReport。
        """
        dataset = self.to_ragas_dataset(samples, contexts, answers)
        result = evaluate(
            dataset=dataset,
            metrics=[
                context_precision,
                context_recall,
                faithfulness,
                answer_relevancy,
            ],
            llm=llm or self._build_ragas_llm(),
            embeddings=embeddings or self._build_ragas_embeddings(),
        )

        score_rows = self._extract_scores(result, len(samples))
        token_list = tokens or [0] * len(samples)
        query_scores: list[RagQueryScore] = []
        for i, sample in enumerate(samples):
            row = score_rows[i] if i < len(score_rows) else {}
            query_scores.append(
                RagQueryScore(
                    sample_id=sample.id,
                    context_precision=self._to_float(row.get("context_precision")),
                    context_recall=self._to_float(row.get("context_recall")),
                    faithfulness=self._to_float(row.get("faithfulness")),
                    answer_relevancy=self._to_float(row.get("answer_relevancy")),
                    retrieved_count=len(contexts[i]),
                    reflection_rounds=self._pipeline.max_reflection_rounds,
                    total_tokens=token_list[i],
                )
            )

        return RagEvalReport(
            dataset_version=dataset_version,
            config=config or {},
            summary=self._build_summary(query_scores),
            queries=query_scores,
        )

    async def evaluate_async(
        self,
        samples: list[RagSample],
        config: dict[str, Any] | None = None,
        dataset_version: str = "1.0",
    ) -> RagEvalReport:
        """异步执行完整评测（检索 + 回答 + ragas 评分）。

        Args:
            samples: RAG 样本列表。
            config: 检索配置。
            dataset_version: 数据集版本。

        Returns:
            RagEvalReport。
        """
        self._apply_config(config)
        contexts: list[list[str]] = []
        answers: list[str] = []
        tokens: list[int] = []
        for sample in samples:
            ctx, answer, _ = await self.retrieve_and_answer(sample, config)
            contexts.append([doc.text for doc in ctx.results])
            answers.append(answer)
            tokens.append(int(getattr(ctx, "total_tokens", 0) or 0))
        return self.evaluate(
            samples=samples,
            contexts=contexts,
            answers=answers,
            config=config,
            dataset_version=dataset_version,
            tokens=tokens,
        )

    async def evaluate_ab_reflection(
        self,
        samples: list[RagSample],
        config: dict[str, Any] | None = None,
        dataset_version: str = "1.0",
    ) -> dict[str, Any]:
        """反思 A/B 对比（只验证、不改逻辑）。

        对同一数据集分别以 reflection=true / false 跑两组完整评测
        （各自独立检索 + 回答 + ragas 评分），输出指标对比摘要。

        Args:
            samples: RAG 样本列表。
            config: 基础检索配置。
            dataset_version: 数据集版本。

        Returns:
            含 off/on 两组报告与 diff 对比摘要的 dict。
        """
        base = dict(config or {})
        off_cfg = {**base, "reflection": False}
        on_cfg = {**base, "reflection": True}

        off_report = await self.evaluate_async(samples, off_cfg, dataset_version)
        on_report = await self.evaluate_async(samples, on_cfg, dataset_version)

        diff = {
            "context_precision": on_report.summary.avg_context_precision
            - off_report.summary.avg_context_precision,
            "context_recall": on_report.summary.avg_context_recall
            - off_report.summary.avg_context_recall,
            "faithfulness": on_report.summary.avg_faithfulness
            - off_report.summary.avg_faithfulness,
        }
        return {
            "reflection_off": off_report,
            "reflection_on": on_report,
            "diff": diff,
        }

    @staticmethod
    def _extract_scores(result: Any, count: int) -> list[dict[str, Any]]:
        """从 ragas EvaluationResult 提取每样本得分。

        Args:
            result: ragas evaluate 返回值。
            count: 样本数。

        Returns:
            每样本得分 dict 列表。
        """
        scores = getattr(result, "scores", None)
        if isinstance(scores, list):
            return [dict(s) if isinstance(s, dict) else {} for s in scores]
        try:
            df = result.to_pandas()
            return df.to_dict("records")  # type: ignore[no-any-return]
        except Exception:
            return [{}] * count

    @staticmethod
    def _to_float(value: Any) -> float:
        """安全转 float。

        Args:
            value: 任意值。

        Returns:
            float 值，无效时返回 0.0。
        """
        try:
            return float(value) if value is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    @staticmethod
    def _build_summary(query_scores: list[RagQueryScore]) -> RagEvalSummary:
        """汇总得分。

        Args:
            query_scores: 每条查询得分。

        Returns:
            RagEvalSummary。
        """
        n = len(query_scores)
        if n == 0:
            return RagEvalSummary()
        return RagEvalSummary(
            samples=n,
            avg_context_precision=round(sum(q.context_precision for q in query_scores) / n, 4),
            avg_context_recall=round(sum(q.context_recall for q in query_scores) / n, 4),
            avg_faithfulness=round(sum(q.faithfulness for q in query_scores) / n, 4),
            avg_answer_relevancy=round(sum(q.answer_relevancy for q in query_scores) / n, 4),
        )
