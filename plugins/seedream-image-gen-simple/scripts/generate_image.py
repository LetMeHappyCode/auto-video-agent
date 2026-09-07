#!/usr/bin/env python
"""火山方舟 Seedream 文生图/图生图命令行工具，无日志记录，直接输出 JSON 结果。

用法示例：
  python generate_image.py --prompt "一只猫在窗台看夕阳"
  python generate_image.py --prompt "生成4张连贯插画" --sequential --max-images 4
  python generate_image.py --prompt "把衣服换成图2的" --image url1 url2
"""
import argparse
import json
import os
import sys
from pathlib import Path

from volcenginesdkarkruntime import Ark
from volcenginesdkarkruntime.types.images.images import SequentialImageGenerationOptions

DEFAULT_MODEL = "doubao-seedream-5-0-260128"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


def main() -> None:
    parser = argparse.ArgumentParser(description="调用方舟 Seedream 接口生成图片")
    parser.add_argument("--prompt", required=True, help="生成提示词")
    parser.add_argument("--image", nargs="*", default=None, help="参考图 URL，可传多个用于图生图")
    parser.add_argument("--sequential", action="store_true", help="生成组图")
    parser.add_argument("--max-images", type=int, default=1, help="组图模式下最多生成的图片数量")
    parser.add_argument("--size", default="2K", help="图片尺寸，如 2K/1K/2048x2048")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="模型 ID")
    parser.add_argument("--no-watermark", action="store_true", help="不添加水印")
    args = parser.parse_args()

    _load_env_file()
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        print(json.dumps({"error": "环境变量 ARK_API_KEY 未设置"}, ensure_ascii=False))
        sys.exit(1)

    client = Ark(base_url=os.environ.get("ARK_BASE_URL", DEFAULT_BASE_URL), api_key=api_key)

    params = {
        "model": args.model,
        "prompt": args.prompt,
        "response_format": "url",
        "size": args.size,
        "watermark": not args.no_watermark,
    }
    if args.image:
        params["image"] = args.image[0] if len(args.image) == 1 else args.image

    try:
        if args.sequential:
            params["sequential_image_generation"] = "auto"
            params["sequential_image_generation_options"] = SequentialImageGenerationOptions(
                max_images=args.max_images
            )
            params["stream"] = True

            response = client.images.generate(**params)
            images = []
            errors = []
            usage = None
            for event in response:
                if event is None:
                    continue
                if event.type == "image_generation.partial_failed":
                    errors.append(str(event.error))
                elif event.type == "image_generation.partial_succeeded" and event.error is None:
                    images.append({"url": event.url, "size": getattr(event, "size", None)})
                elif event.type == "image_generation.completed" and event.error is None:
                    usage = event.usage

            result = {
                "images": images,
                "usage": usage.model_dump() if hasattr(usage, "model_dump") else usage,
                "errors": errors,
            }
        else:
            params["sequential_image_generation"] = "disabled"
            params["stream"] = False
            response = client.images.generate(**params)
            images = [{"url": item.url} for item in (response.data or [])]
            usage = getattr(response, "usage", None)
            result = {
                "images": images,
                "usage": usage.model_dump() if hasattr(usage, "model_dump") else usage,
                "errors": [],
            }

        print(json.dumps(result, ensure_ascii=False))
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()
