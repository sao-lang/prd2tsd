"""统一图片编码能力 — API 优先，本地 CLIP 模型兜底。

策略：
  1. API 模式：调用多模态 LLM API（如 GPT-4o 生成图片描述向量，预留接口）
  2. 本地模式：使用 transformers CLIP 双塔模型
  3. 自动降级：API 不可用时自动回退到本地模型

配置（环境变量 / .env / 代码默认值）：
  MODEL_CONFIG__VISION__OPENAI__API_KEY       （预留，未来 API 图片编码用）
  MODEL_CONFIG__VISION__OPENAI__BASE_URL
  MODEL_CONFIG__VISION__OPENAI__DEFAULT_MODEL
  IMAGE_ENCODE_MODE=auto|api|local
  CLIP_MODEL_NAME=openai/clip-vit-base-patch32
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.gateway.image_encoder")


class UnifiedImageEncoder:
    """统一图片编码能力。

    API 优先（预留），本地 CLIP 模型兜底。
    """

    def __init__(
        self,
        mode: str = "auto",
        clip_model_name: str = "openai/clip-vit-base-patch32",
    ) -> None:
        """初始化统一图片编码器。

        Args:
            mode: 运行模式（auto/api/local）。
            clip_model_name: 本地 CLIP 模型名称。
        """
        self._mode = mode
        self._clip_model_name = clip_model_name
        self._clip_model: Any = None
        self._clip_processor: Any = None

    async def encode_image(
        self,
        image_bytes: bytes,
        mode: str | None = None,
    ) -> list[float]:
        """编码图片为视觉向量。

        Args:
            image_bytes: 图片字节数据。
            mode: 临时覆盖运行模式。

        Returns:
            视觉向量。
        """
        effective_mode = mode or self._mode

        # API 优先（预留）
        if effective_mode in ("auto", "api"):
            try:
                return await self._api_encode_image(image_bytes)
            except Exception as exc:
                if effective_mode == "api":
                    raise
                logger.warning("API 图片编码失败，降级到本地 CLIP: %s", exc)

        # 本地 CLIP 兜底
        return await self._local_encode_image(image_bytes)

    async def encode_text(
        self,
        text: str,
        mode: str | None = None,
    ) -> list[float]:
        """编码文本为文本向量（与 encode_image 共享语义空间）。

        Args:
            text: 输入文本。
            mode: 临时覆盖运行模式。

        Returns:
            文本向量。
        """
        effective_mode = mode or self._mode

        if effective_mode in ("auto", "api"):
            try:
                return await self._api_encode_text(text)
            except Exception as exc:
                if effective_mode == "api":
                    raise
                logger.warning("API 文本编码失败，降级到本地 CLIP: %s", exc)

        return await self._local_encode_text(text)

    async def _api_encode_image(self, image_bytes: bytes) -> list[float]:
        """预留：通过 API 编码图片。

        Args:
            image_bytes: 图片字节数据。

        Returns:
            向量。

        Raises:
            NotImplementedError: API 图片编码尚未实现。
        """
        raise NotImplementedError("API 图片编码尚未实现，请使用 local 模式")

    async def _api_encode_text(self, text: str) -> list[float]:
        """预留：通过 API 编码文本。

        Args:
            text: 输入文本。

        Returns:
            向量。

        Raises:
            NotImplementedError: API 文本编码尚未实现。
        """
        raise NotImplementedError("API 文本编码尚未实现，请使用 local 模式")

    async def _local_encode_image(self, image_bytes: bytes) -> list[float]:
        """通过本地 CLIP 模型编码图片。

        Args:
            image_bytes: 图片字节数据。

        Returns:
            512 维向量。
        """
        model, processor = self._ensure_loaded()
        if model is None or processor is None:
            return self._mock_embedding()

        try:
            import io

            import torch
            from PIL import Image

            img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
            inputs = processor(images=img, return_tensors="pt")
            with torch.no_grad():
                emb = model.get_image_features(**inputs)
            return emb[0].tolist()
        except Exception as exc:
            logger.warning("CLIP 图片编码失败: %s，使用模拟向量", exc)
            return self._mock_embedding()

    async def _local_encode_text(self, text: str) -> list[float]:
        """通过本地 CLIP 模型编码文本。

        Args:
            text: 输入文本。

        Returns:
            512 维向量。
        """
        model, processor = self._ensure_loaded()
        if model is None or processor is None:
            return self._mock_embedding()

        try:
            import torch

            inputs = processor(text=[text], return_tensors="pt", padding=True)
            with torch.no_grad():
                emb = model.get_text_features(**inputs)
            return emb[0].tolist()
        except Exception as exc:
            logger.warning("CLIP 文本编码失败: %s，使用模拟向量", exc)
            return self._mock_embedding()

    def _ensure_loaded(self) -> tuple[Any, Any]:
        """延迟加载 CLIP 模型。

        Returns:
            (model, processor) 元组。
        """
        if self._clip_model is None:
            try:
                from transformers import CLIPModel, CLIPProcessor

                logger.info("加载 CLIP 模型: %s", self._clip_model_name)
                self._clip_model = CLIPModel.from_pretrained(self._clip_model_name)
                self._clip_processor = CLIPProcessor.from_pretrained(self._clip_model_name)
            except Exception as exc:
                logger.warning("CLIP 模型加载失败: %s，使用模拟向量", exc)
                return None, None

        return self._clip_model, self._clip_processor

    @staticmethod
    def _mock_embedding() -> list[float]:
        """生成模拟向量（模型不可用时的兜底）。"""
        vec = [0.01 * (i % 10 - 5) for i in range(512)]
        magnitude = sum(v * v for v in vec) ** 0.5
        return [v / magnitude for v in vec]

    @property
    def mode(self) -> str:
        """当前运行模式。"""
        return self._mode

    @mode.setter
    def mode(self, value: str) -> None:
        """设置运行模式。

        Args:
            value: auto / api / local。
        """
        if value not in ("auto", "api", "local"):
            raise ValueError(f"无效模式: {value}，可选 auto/api/local")
        self._mode = value
        logger.info("图片编码模式已切换: %s", value)
