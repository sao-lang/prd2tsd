"""图片预览与缩略图生成。"""

from __future__ import annotations

import io
from typing import Any

from app.core.logger import get_logger

logger = get_logger("prd2tsd.image_preview")

# 检查 pillow 是否可用
try:
    from PIL import Image as PILImage
    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    PILImage = None  # type: ignore[assignment]


class ImagePreviewGenerator:
    """图片预览生成器。

    支持生成缩略图和获取图片基本信息。
    """

    MAX_THUMBNAIL_SIZE = (300, 300)

    async def generate_thumbnail(
        self,
        image_bytes: bytes,
        max_size: tuple[int, int] | None = None,
    ) -> dict[str, Any]:
        """生成缩略图。

        Args:
            image_bytes: 原始图片数据。
            max_size: 缩略图最大尺寸。

        Returns:
            {"thumbnail": bytes, "width": int, "height": int, "format": str}
        """
        if not HAS_PILLOW:
            return {
                "thumbnail": image_bytes,
                "width": 0,
                "height": 0,
                "format": "unknown",
                "error": "pillow 未安装",
            }

        try:
            img = PILImage.open(io.BytesIO(image_bytes))  # type: ignore[union-attr]
            fmt = img.format or "PNG"
            w, h = img.size

            size = max_size or self.MAX_THUMBNAIL_SIZE
            img.thumbnail(size, PILImage.Resampling.LANCZOS)  # type: ignore[union-attr]

            buf = io.BytesIO()
            img.save(buf, format=fmt)
            thumbnail_bytes = buf.getvalue()

            return {
                "thumbnail": thumbnail_bytes,
                "width": w,
                "height": h,
                "format": fmt.lower(),
                "error": None,
            }
        except Exception as exc:
            logger.warning("缩略图生成失败: %s", exc)
            return {
                "thumbnail": image_bytes,
                "width": 0,
                "height": 0,
                "format": "unknown",
                "error": str(exc),
            }

    async def get_image_info(self, image_bytes: bytes) -> dict[str, Any]:
        """获取图片基本信息。

        Args:
            image_bytes: 图片数据。

        Returns:
            {"width": int, "height": int, "format": str, "size_bytes": int}
        """
        info: dict[str, Any] = {
            "width": 0,
            "height": 0,
            "format": "unknown",
            "size_bytes": len(image_bytes),
        }

        if HAS_PILLOW:
            try:
                img = PILImage.open(io.BytesIO(image_bytes))  # type: ignore[union-attr]
                info["width"] = img.width
                info["height"] = img.height
                info["format"] = (img.format or "UNKNOWN").lower()
            except Exception:
                pass

        return info
