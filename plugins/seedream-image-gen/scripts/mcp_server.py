"""Seedream 图片生成插件的 MCP 服务器，暴露文生图/图生图工具。"""
import sys
from pathlib import Path
from typing import Optional, Union

sys.path.insert(0, str(Path(__file__).resolve().parent))

from mcp.server.fastmcp import FastMCP
from ark_image_client import ArkImageError, generate_image

mcp = FastMCP("seedream-image-gen")


@mcp.tool()
def generate_images(
    prompt: str,
    image: Optional[Union[str, list[str]]] = None,
    sequential: bool = False,
    max_images: int = 1,
    size: str = "2K",
    watermark: bool = True,
) -> dict:
    """
    使用火山方舟 Seedream 模型生成图片，支持文生图和图生图，支持单图和组图。

    Args:
        prompt: 图片生成提示词，描述画面内容、风格等。
        image: 参考图 URL。不传则为纯文生图；传单个字符串为单图参考；
               传字符串列表为多图参考（用于图生图/风格迁移等场景）。
        sequential: 是否生成一组连贯的图片。False 为单张图，True 为组图。
        max_images: sequential=True 时最多生成的图片数量（建议 2-15）。
        size: 输出图片尺寸，默认 "2K"。
        watermark: 是否为生成图片添加水印，默认 True。

    Returns:
        包含 request_id、images（每张图的 url）、usage、errors 的字典。
        所有请求和响应都会记录到插件的 logs/image_gen.log 中，便于排查问题。
    """
    try:
        return generate_image(
            prompt=prompt,
            image=image,
            sequential=sequential,
            max_images=max_images,
            size=size,
            watermark=watermark,
        )
    except ArkImageError as exc:
        return {"error": str(exc)}


if __name__ == "__main__":
    mcp.run(transport="stdio")
