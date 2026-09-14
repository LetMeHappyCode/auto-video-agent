#!/usr/bin/env python3
"""批量调用 doubao-seedream 为 shots 目录下的每个 prompt 生成插画图片。

has_protagonist=true 的 shot 使用图生图（传参考图保持主角一致性），
has_protagonist=false 的 shot 使用纯文生图。

用法：
    批量：python scripts/generate_images.py --dir <shots目录>
    单张：python scripts/generate_images.py --dir <shots目录> --shot-id 1

环境变量：
    ARK_API_KEY  方舟 API Key
"""

import argparse
import asyncio
import base64
import json
import mimetypes
import os
import sys
import time
import urllib.request
from pathlib import Path

try:
    from arkruntime import Ark
except ImportError:
    try:
        from volcenginesdkarkruntime import Ark
    except ImportError:
        print("请安装方舟 SDK：\n"
              "  新版：pip install arkruntime\n"
              "  旧版：pip install \"volcengine-python-sdk[ark]\"", file=sys.stderr)
        sys.exit(1)


def load_env():
    """从项目根目录的 .env 文件加载环境变量"""
    script_dir = Path(__file__).parent
    project_root = script_dir.parent
    env_file = project_root / ".env"

    if env_file.exists():
        with open(env_file, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, value = line.split("=", 1)
                    key = key.strip()
                    value = value.strip()
                    if key and value and key not in os.environ:
                        os.environ[key] = value


def to_image_input(ref_image: str) -> str:
    """将本地图片路径转换为方舟 API 要求的 data:image/<fmt>;base64,<data> 格式；
    已经是 URL（http/https）的直接原样返回。"""
    if ref_image.startswith("http://") or ref_image.startswith("https://"):
        return ref_image

    path = Path(ref_image)
    mime, _ = mimetypes.guess_type(path.name)
    if not mime or not mime.startswith("image/"):
        mime = "image/png"
    fmt = mime.split("/", 1)[1].lower()
    data = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{fmt};base64,{data}"


def load_shots(dir_path: Path) -> list[dict]:
    files = sorted(dir_path.glob("shot-*.prompt.json"))
    shots = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            shots.append({
                "shot_id": data["shot_id"],
                "prompt": data["prompt"],
                "has_protagonist": data.get("has_protagonist", True),
                "source_path": f,
            })
        except (json.JSONDecodeError, KeyError) as e:
            print(f"  跳过 {f.name}：{e}", file=sys.stderr)
    return shots


def generate_one(client: Ark, shot: dict, out_dir: Path, model: str,
                 size: str, skip_existing: bool, ref_image: str | None) -> dict:
    shot_id = shot["shot_id"]
    out_path = out_dir / f"shot-{shot_id:04d}.png"
    result = {"shot_id": shot_id, "status": "pending", "path": str(out_path), "error": ""}

    if skip_existing and out_path.exists():
        result["status"] = "skipped"
        return result

    try:
        kwargs = dict(
            model=model,
            prompt=shot["prompt"],
            size=size,
            output_format="png",
            response_format="url",
            watermark=False,
        )
        if shot["has_protagonist"] and ref_image:
            kwargs["image"] = ref_image

        resp = client.images.generate(**kwargs)
        url = resp.data[0].url

        urllib.request.urlretrieve(url, str(out_path))
        result["status"] = "success"
    except Exception as e:
        result["status"] = "failed"
        result["error"] = str(e)

    return result


def main() -> None:
    load_env()  # 加载 .env 文件

    parser = argparse.ArgumentParser(description="批量为 shot prompt 生成插画图片")
    parser.add_argument("--dir", type=Path, required=True, help="shots 目录绝对路径")
    parser.add_argument("--ref-image", default=None, help="主角参考图路径（本地路径或 URL），不传则全部走纯文生图")
    parser.add_argument("--model", default="doubao-seedream-5-0-lite-260128", help="模型 ID")
    parser.add_argument("--size", default="1440x2560", help="图片尺寸，默认 9:16 竖屏")
    parser.add_argument("--concurrency", type=int, default=3, help="并发数")
    parser.add_argument("--skip-existing", action="store_true", help="跳过已有图片")
    parser.add_argument("--shot-id", type=int, default=None, help="只生成指定 shot（用于测试或重试单张）")
    args = parser.parse_args()

    api_key = os.getenv("ARK_API_KEY")
    if not api_key:
        print("错误：请设置环境变量 ARK_API_KEY", file=sys.stderr)
        sys.exit(1)

    dir_path = args.dir.resolve()
    if not dir_path.is_dir():
        print(f"错误：目录不存在 {dir_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = dir_path.parent / "images"
    out_dir.mkdir(exist_ok=True)

    ref_image = args.ref_image
    if ref_image:
        ref_path = Path(ref_image)
        if ref_path.exists():
            ref_image = to_image_input(str(ref_path.resolve()))
        else:
            ref_image = to_image_input(ref_image)
    else:
        print("未传 --ref-image，所有 shot 均走纯文生图")

    shots = load_shots(dir_path)
    if not shots:
        print("未找到 shot-*.prompt.json 文件", file=sys.stderr)
        sys.exit(1)

    if args.shot_id is not None:
        shots = [s for s in shots if s["shot_id"] == args.shot_id]
        if not shots:
            print(f"错误：未找到 shot_id={args.shot_id} 的文件", file=sys.stderr)
            sys.exit(1)
        print(f"单张模式：shot-{args.shot_id:04d}")
    else:
        with_ref = sum(1 for s in shots if s["has_protagonist"])
        without_ref = len(shots) - with_ref
        print(f"找到 {len(shots)} 个 shot（{with_ref} 个含主角用图生图，{without_ref} 个纯文生图）")
    print(f"模型: {args.model}  尺寸: {args.size}  并发: {args.concurrency}")
    print(f"输出目录: {out_dir}")
    print()

    client = Ark(
        base_url="https://ark.cn-beijing.volces.com/api/v3",
        api_key=api_key,
    )

    sem = asyncio.Semaphore(args.concurrency)

    async def gen_with_limit(shot: dict) -> dict:
        async with sem:
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(
                None, generate_one, client, shot, out_dir,
                args.model, args.size, args.skip_existing, ref_image,
            )

    async def run_all():
        tasks = [gen_with_limit(s) for s in shots]
        results = []
        for coro in asyncio.as_completed(tasks):
            r = await coro
            tag = "✓" if r["status"] == "success" else "✗" if r["status"] == "failed" else "→"
            print(f"  {tag} shot-{r['shot_id']:04d}  {r['status']}"
                  + (f"  {r['error']}" if r["error"] else ""))
            results.append(r)
        return results

    t0 = time.time()
    results = asyncio.run(run_all())
    elapsed = time.time() - t0

    succeeded = sum(1 for r in results if r["status"] == "success")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = [r for r in results if r["status"] == "failed"]

    print()
    print(f"完成：{succeeded} 成功 / {skipped} 跳过 / {len(failed)} 失败  "
          f"耗时 {elapsed:.1f}s")

    if failed:
        print("\n失败列表：")
        for r in sorted(failed, key=lambda x: x["shot_id"]):
            print(f"  shot-{r['shot_id']:04d}: {r['error']}")
        sys.exit(1)


if __name__ == "__main__":
    main()
