#!/usr/bin/env python3
"""把各 segment 的精切结果（segment-000N.json）确定性合并为最终 shots.json。

纯代码拼接，不经过 AI：
- 按 segment_id 顺序拼接 shots 数组，id 重新从 1 连续编号。
- source_srt_ids 保持原样（segment SRT 保留了原始全局 cue index，天然是全局编号）。
- 合并后校验 source_srt_ids 覆盖 1..total_cues 且无重复无缺失。
- 原子写入 result_path（先写临时文件再替换）。
"""

import argparse
import json
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="合并 segment 精切结果为最终 shots.json")
    parser.add_argument("--source-srt", type=str, required=True, help="原始 SRT 文件路径（写入最终 JSON 的 source_srt 字段）")
    parser.add_argument("--total-cues", type=int, required=True, help="原始 SRT 的总 cue 数")
    parser.add_argument("--segment", action="append", required=True,
                         help="按顺序传入的 segment 精切结果文件绝对路径，可重复传入多次，顺序即 segment_id 顺序")
    parser.add_argument("--result-path", type=Path, required=True, help="最终 shots.json 的绝对写入路径")
    args = parser.parse_args()

    all_shots = []
    seen_source_ids = set()
    error = None

    for seg_path_str in args.segment:
        seg_path = Path(seg_path_str)
        if not seg_path.exists():
            error = f"segment 结果文件不存在：{seg_path}"
            break
        try:
            data = json.loads(seg_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            error = f"segment 结果文件 JSON 解析失败（可能是半截写入）：{seg_path}"
            break

        seg_shots = data.get("shots", [])
        if not seg_shots:
            error = f"segment 结果文件没有 shots 或为空：{seg_path}"
            break

        for shot in seg_shots:
            src_ids = shot.get("source_srt_ids", [])
            for sid in src_ids:
                if sid in seen_source_ids:
                    error = f"cue index {sid} 在多个 shot/segment 中重复出现（来自 {seg_path}）"
                    break
                seen_source_ids.add(sid)
            if error:
                break
            all_shots.append({
                "start": shot["start"],
                "end": shot["end"],
                "text": shot["text"],
                "source_srt_ids": src_ids,
            })
        if error:
            break

    if error is None:
        expected = set(range(1, args.total_cues + 1))
        if seen_source_ids != expected:
            missing = sorted(expected - seen_source_ids)
            extra = sorted(seen_source_ids - expected)
            error = f"合并后 source_srt_ids 未覆盖全部 cue（缺失 {missing}，多余 {extra}）"

    if error:
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False))
        return

    for i, shot in enumerate(all_shots, start=1):
        shot["id"] = i
    for shot in all_shots:
        shot_ordered = {
            "id": shot["id"],
            "start": shot["start"],
            "end": shot["end"],
            "text": shot["text"],
            "source_srt_ids": shot["source_srt_ids"],
        }
        shot.clear()
        shot.update(shot_ordered)

    final = {
        "source_srt": args.source_srt,
        "total_cues": args.total_cues,
        "total_shots": len(all_shots),
        "shots": all_shots,
    }

    tmp_path = args.result_path.with_suffix(args.result_path.suffix + ".tmp")
    args.result_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path.write_text(json.dumps(final, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(args.result_path)

    print(json.dumps({
        "ok": True,
        "result_path": str(args.result_path),
        "total_cues": args.total_cues,
        "total_shots": len(all_shots),
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
