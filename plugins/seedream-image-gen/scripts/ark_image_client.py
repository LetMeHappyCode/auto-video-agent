"""火山方舟 Seedream 文生图/图生图核心封装，含请求/响应日志记录。"""
import json
import logging
import os
import time
import uuid
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any, Optional, Union

from dotenv import load_dotenv
from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.images.images import SequentialImageGenerationOptions

PLUGIN_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PLUGIN_ROOT / ".env")
LOG_DIR = Path(os.environ.get("SEEDREAM_LOG_DIR", PLUGIN_ROOT / "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_MODEL = "doubao-seedream-5-0-260128"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger("seedream_image_gen")
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(
        LOG_DIR / "image_gen.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    return logger


_logger = _build_logger()


class ArkImageError(RuntimeError):
    """封装 Ark 图像生成调用失败时的错误信息。"""


def _log_record(record: dict) -> None:
    _logger.info(json.dumps(record, ensure_ascii=False, default=str))


def _get_client() -> Ark:
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        raise ArkImageError("环境变量 ARK_API_KEY 未设置，请先配置方舟 API Key")
    base_url = os.environ.get("ARK_BASE_URL", DEFAULT_BASE_URL)
    return Ark(base_url=base_url, api_key=api_key)


def generate_image(
    prompt: str,
    image: Optional[Union[str, list]] = None,
    sequential: bool = False,
    max_images: int = 1,
    size: str = "2K",
    model: str = DEFAULT_MODEL,
    watermark: bool = True,
    response_format: str = "url",
) -> dict:
    """
    调用方舟 Seedream 接口生成图片，支持文生图/图生图、单图/组图。

    Args:
        prompt: 生成提示词。
        image: 参考图 URL（单个字符串）或多张参考图 URL 列表；为空则为纯文生图。
        sequential: 是否生成组图（对应 sequential_image_generation="auto"）。
        max_images: 组图模式下最多生成的图片数量（1-15，由 API 侧限制）。
        size: 图片尺寸，如 "2K"。
        model: 模型 ID。
        watermark: 是否添加水印。
        response_format: 返回格式，"url" 或 "b64_json"。

    Returns:
        dict，包含 request_id、图片 URL 列表、usage 等信息。
    """
    request_id = uuid.uuid4().hex[:12]
    started_at = time.time()

    params: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "response_format": response_format,
        "size": size,
        "watermark": watermark,
    }
    if image is not None:
        params["image"] = image

    is_stream = sequential
    if sequential:
        params["sequential_image_generation"] = "auto"
        params["sequential_image_generation_options"] = SequentialImageGenerationOptions(
            max_images=max_images
        )
        params["stream"] = True
    else:
        params["sequential_image_generation"] = "disabled"
        params["stream"] = False

    log_input = {k: v for k, v in params.items()}
    if isinstance(log_input.get("sequential_image_generation_options"), SequentialImageGenerationOptions):
        log_input["sequential_image_generation_options"] = {"max_images": max_images}

    _log_record({
        "request_id": request_id,
        "event": "request",
        "timestamp": started_at,
        "input": log_input,
    })

    try:
        client = _get_client()
        response = client.images.generate(**params)

        if is_stream:
            images: list[dict] = []
            usage = None
            errors = []
            for event in response:
                if event is None:
                    continue
                if event.type == "image_generation.partial_failed":
                    errors.append(str(event.error))
                elif event.type == "image_generation.partial_succeeded":
                    if event.error is None:
                        images.append({
                            "url": getattr(event, "url", None),
                            "size": getattr(event, "size", None),
                        })
                elif event.type == "image_generation.completed":
                    if event.error is None:
                        usage = getattr(event, "usage", None)
                    else:
                        errors.append(str(event.error))

            result = {
                "request_id": request_id,
                "images": images,
                "usage": usage.model_dump() if hasattr(usage, "model_dump") else usage,
                "errors": errors,
            }
        else:
            data = response.data or []
            images = [
                {
                    "url": getattr(item, "url", None),
                    "b64_json": getattr(item, "b64_json", None),
                }
                for item in data
            ]
            usage = getattr(response, "usage", None)
            result = {
                "request_id": request_id,
                "images": images,
                "usage": usage.model_dump() if hasattr(usage, "model_dump") else usage,
                "errors": [],
            }

        elapsed = time.time() - started_at
        _log_record({
            "request_id": request_id,
            "event": "response",
            "timestamp": time.time(),
            "elapsed_seconds": round(elapsed, 3),
            "output": result,
        })
        return result

    except Exception as exc:
        elapsed = time.time() - started_at
        _log_record({
            "request_id": request_id,
            "event": "error",
            "timestamp": time.time(),
            "elapsed_seconds": round(elapsed, 3),
            "error": str(exc),
            "error_type": type(exc).__name__,
        })
        raise ArkImageError(f"图片生成失败: {exc}") from exc
