#!/usr/bin/env python3
"""按 coarse.json 给出的 cue 区间，把整份 SRT 确定性地切成多个 segment SRT 文件。

纯代码切分，不依赖 AI 转录 cue 内容/时间戳，避免粗切阶段引入幻觉。
每个 segment SRT 文件保留原始全局 cue index（不重新从 1 编号），
这样后续精切结果里的 source_srt_ids 天然就是全局编号，合并阶段不需要额外的映射表。
"""

import argparse
import json
import re
from pathlib import Path

CUE_RE = re.compile(
    r"(?P<index>\d+)\s*\r?\n"
    r"(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(?P<end>\d{2}:\d{2}:\d{2},\d{3})[^\r\n]*\r?\n"
    r"(?P<text>.*?)(?=\r?\n\r?\n|\Z)",
    re.DOTALL,
)


def parse_srt(srt_text: str) -> list[dict]:
    cues = []
    for m in CUE_RE.finditer(srt_text.strip() + "\n\n"):
        index = int(m.group("index"))
        text = m.group("text").strip()
        if not text:
            continue
        cues.append({
            "index": index,
            "start": m.group("start"),
            "end": m.group("end"),
            "text": text,
        })
    cues.sort(key=lambda c: c["index"])
    return cues


def render_cue(cue: dict) -> str:
    return f"{cue['index']}\n{cue['start']} --> {cue['end']}\n{cue['text']}\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="按 coarse.json 的 cue 区间切分 SRT")
    parser.add_argument("--source-srt", type=Path, required=True, help="原始 SRT 文件绝对路径")
    parser.add_argument("--coarse", type=Path, required=True, help="粗切 agent 落盘的 coarse.json 绝对路径")
    parser.add_argument("--out-dir", type=Path, required=True, help="segment SRT 文件输出目录（shots.json.build/）")
    args = parser.parse_args()

    srt_text = args.source_srt.read_text(encoding="utf-8")
    cues = parse_srt(srt_text)
    total_cues = len(cues)

    coarse = json.loads(args.coarse.read_text(encoding="utf-8"))
    segments = coarse.get("segments", [])

    if coarse.get("total_cues") != total_cues:
        print(json.dumps({
            "ok": False,
            "error": f"coarse.json 的 total_cues={coarse.get('total_cues')} 与实际解析出的 {total_cues} 条不一致",
        }, ensure_ascii=False))
        return

    cues_by_index = {c["index"]: c for c in cues}
    all_indices = sorted(cues_by_index.keys())

    covered = set()
    seg_infos = []
    error = None

    sorted_segments = sorted(segments, key=lambda s: s["segment_id"])
    prev_end = None
    for seg in sorted_segments:
        seg_id = seg["segment_id"]
        cue_start = seg["cue_start"]
        cue_end = seg["cue_end"]

        if prev_end is not None and cue_start != prev_end + 1:
            error = f"segment {seg_id} 的 cue_start={cue_start} 与前一段末尾 {prev_end} 不连续"
            break
        prev_end = cue_end

        seg_cues = [cues_by_index[i] for i in range(cue_start, cue_end + 1) if i in cues_by_index]
        if len(seg_cues) != (cue_end - cue_start + 1):
            missing = [i for i in range(cue_start, cue_end + 1) if i not in cues_by_index]
            error = f"segment {seg_id} 区间 [{cue_start},{cue_end}] 缺少 cue index：{missing}"
            break

        covered.update(range(cue_start, cue_end + 1))

        out_path = args.out_dir / f"segment-{seg_id:04d}.srt"
        body = "\n".join(render_cue(c) for c in seg_cues)
        out_path.write_text(body, encoding="utf-8")

        seg_infos.append({
            "segment_id": seg_id,
            "cue_start": cue_start,
            "cue_end": cue_end,
            "cue_count": len(seg_cues),
            "srt_path": str(out_path),
            "time_start": seg_cues[0]["start"],
            "time_end": seg_cues[-1]["end"],
        })

    if error is None and covered != set(all_indices):
        missing = sorted(set(all_indices) - covered)
        extra = sorted(covered - set(all_indices))
        error = f"分区未完全覆盖全部 cue（缺失 {missing}，多余 {extra}）"

    if error:
        print(json.dumps({"ok": False, "error": error}, ensure_ascii=False))
        return

    print(json.dumps({
        "ok": True,
        "total_cues": total_cues,
        "segments": seg_infos,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
