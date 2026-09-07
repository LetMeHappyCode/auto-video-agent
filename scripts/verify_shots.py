#!/usr/bin/env python3
"""批量校验 output_dir 下的 shot-NNNN.prompt.json 结果文件

只做只读结构性校验：文件存在性、JSON 合法性、shot_id 匹配、必需字段齐全、
prompt 非空且不含换行。不解读 prompt/当前目标片段 的内容质量。
"""

import argparse
import json
from pathlib import Path


def file_name_for(shot_id: int) -> str:
    return f"shot-{shot_id:04d}.prompt.json"


def verify_one(dir_path: Path, shot_id: int) -> dict:
    result_path = dir_path / file_name_for(shot_id)
    entry = {
        "shot_id": shot_id,
        "result_path": str(result_path),
        "verified": False,
        "error": "",
    }

    if not result_path.exists():
        entry["error"] = "result_path 指向的文件不存在"
        return entry

    try:
        raw = result_path.read_text(encoding="utf-8")
    except OSError as exc:
        entry["error"] = f"文件读取失败：{exc}"
        return entry

    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        entry["error"] = "JSON 解析失败（可能是半截写入的残片）"
        return entry

    if not isinstance(data, dict):
        entry["error"] = "JSON 顶层不是对象"
        return entry

    if data.get("shot_id") != shot_id:
        entry["error"] = f"shot_id 不匹配（期望 {shot_id}，实际 {data.get('shot_id')!r}）"
        return entry

    scene = data.get("当前目标片段")
    if not isinstance(scene, str) or not scene.strip():
        entry["error"] = "缺少 当前目标片段 字段或为空"
        return entry

    prompt = data.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        entry["error"] = "prompt 字段为空或缺失"
        return entry

    if "\n" in prompt or "\r" in prompt:
        entry["error"] = "prompt 字段包含换行符"
        return entry

    entry["verified"] = True
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="批量校验 shot 提示词结果文件")
    parser.add_argument("--dir", type=Path, required=True, help="output_dir 绝对路径")
    parser.add_argument("--total-shots", type=int, required=True, help="期望存在的 shot 总数（shot_id 从 1 到该值）")
    args = parser.parse_args()

    dir_path = args.dir.resolve()

    results = [verify_one(dir_path, shot_id) for shot_id in range(1, args.total_shots + 1)]

    passed = sum(1 for r in results if r["verified"])
    failed = [r for r in results if not r["verified"]]

    print(json.dumps({
        "dir": str(dir_path),
        "total_shots": args.total_shots,
        "passed": passed,
        "failed_count": len(failed),
        "results": results,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
