"""CLIP 双塔编码器 — 视觉 Embedding（512d）+ 文本 Embedding（512d）。

使用 transformers 库加载 CLIP 模型，将图片和文本映射到同一语义空间。
"""

from __future__ import annotations

from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.clip_encoder")


class ClipEncoder:
    """CLIP 双塔编码器（openai/clip-vit-base-patch32，512d）。

    提供两个接口：
    - encode_image(bytes) → list[float]  视觉 Embedding（512d）
    - encode_text(str) → list[float]     文本 Embedding（512d）

    当前为占位实现，返回随机向量。
    生产环境需安装 `transformers` + `torch` + `pillow`。
    """

    # CLIP ViT-B/32 输出维度（视觉 512d，文本 512d）
    EMBEDDING_DIM = 512

    def __init__(self, model_name: str = "openai/clip-vit-base-patch32") -> None:
        """初始化 CLIP 编码器。

        Args:
            model_name: CLIP 模型名称。
        """
        self.model_name = model_name
        self._model: Any = None
        self._processor: Any = None
        self._loaded = False

    async def _ensure_loaded(self) -> None:
        """延迟加载 CLIP 模型。"""
        if self._loaded:
            return
        try:
            from transformers import CLIPModel, CLIPProcessor

            self._model = CLIPModel.from_pretrained(self.model_name)
            self._processor = CLIPProcessor.from_pretrained(self.model_name)
            self._loaded = True
            logger.info("CLIP 模型已加载: %s", self.model_name)
        except ImportError:
            logger.warning(
                "transformers/torch 未安装，使用模拟 Embedding。"
                "生产环境请安装: pip install transformers torch pillow",
            )
        except Exception as exc:
            logger.warning("CLIP 模型加载失败: %s，使用模拟 Embedding", exc)

    async def encode_image(self, image_bytes: bytes) -> list[float]:
        """编码图片为视觉 Embedding。

        Args:
            image_bytes: 图片字节数据。

        Returns:
            768 维浮点向量。
        """
        await self._ensure_loaded()
        if self._loaded and self._model and self._processor:
            try:
                import io

                import torch
                from PIL import Image

                img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
                inputs = self._processor(images=img, return_tensors="pt")
                with torch.no_grad():
                    emb = self._model.get_image_features(**inputs)
                return emb[0].tolist()
            except Exception as exc:
                logger.warning("CLIP 图片编码失败: %s，使用模拟向量", exc)

        return await self._mock_embedding()

    async def encode_text(self, text: str) -> list[float]:
        """编码文本为文本 Embedding。

        Args:
            text: 输入文本。

        Returns:
            768 维浮点向量。
        """
        await self._ensure_loaded()
        if self._loaded and self._model and self._processor:
            try:
                import torch

                inputs = self._processor(text=[text], return_tensors="pt", padding=True)
                with torch.no_grad():
                    emb = self._model.get_text_features(**inputs)
                return emb[0].tolist()
            except Exception as exc:
                logger.warning("CLIP 文本编码失败: %s，使用模拟向量", exc)

        return await self._mock_embedding()

    @staticmethod
    async def _mock_embedding() -> list[float]:
        """生成模拟 Embedding（模型未加载时使用）。

        返回 768 维单位向量。
        """
        vec = [0.01 * (i % 10 - 5) for i in range(ClipEncoder.EMBEDDING_DIM)]
        magnitude = sum(v * v for v in vec) ** 0.5
        return [v / magnitude for v in vec]
