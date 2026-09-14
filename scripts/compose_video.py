#!/usr/bin/env python3
"""将 shots.json 中每个分镜对应的图片按时间线拼接成一段视频（无声）。

时间轴与 shots.json 完全对齐：每张图片从本分镜 start 开始显示，
一直延续到下一个分镜的 start（有间隙时用当前图片补齐间隙）；
最后一个分镜显示到自己的 end。

用法：
    python scripts/compose_video.py --dir <项目目录，含 shots.json 和 images/>
    python scripts/compose_video.py --dir <项目目录> --output out.mp4 --fps 30

依赖：系统需已安装 ffmpeg 并在 PATH 中可用。
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


def parse_srt_time(ts: str) -> float:
    """"HH:MM:SS,mmm" -> 秒（float）"""
    hms, ms = ts.split(",")
    h, m, s = hms.split(":")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def find_image(images_dir: Path, shot_id: int) -> Path:
    matches = sorted(images_dir.glob(f"shot-{shot_id:04d}.*"))
    if not matches:
        raise FileNotFoundError(f"未找到分镜 {shot_id} 对应的图片（images/shot-{shot_id:04d}.*）")
    return matches[0]


def build_timeline(shots: list[dict]) -> list[tuple[Path, float]]:
    """返回 [(图片路径占位, 显示时长)]，占位由调用方回填真实路径"""
    starts = [parse_srt_time(s["start"]) for s in shots]
    ends = [parse_srt_time(s["end"]) for s in shots]
    timeline = []
    for i, shot in enumerate(shots):
        if i + 1 < len(shots):
            duration = starts[i + 1] - starts[i]
        else:
            duration = ends[i] - starts[i]
        if duration <= 0:
            raise ValueError(f"分镜 {shot['id']} 计算出的显示时长非正数：{duration}")
        timeline.append((shot["id"], duration))
    return timeline


def main() -> None:
    parser = argparse.ArgumentParser(description="按 shots.json 时间线将分镜图片拼接为无声视频")
    parser.add_argument("--dir", type=Path, required=True, help="项目目录（含 shots.json 和 images/）")
    parser.add_argument("--output", type=Path, default=None, help="输出视频路径，默认 <dir>/output.mp4")
    parser.add_argument("--fps", type=int, default=30, help="输出视频帧率，默认 30")
    args = parser.parse_args()

    project_dir = args.dir.resolve()
    shots_json_path = project_dir / "shots.json"
    images_dir = project_dir / "images"
    output_path = (args.output or (project_dir / "output.mp4")).resolve()

    if not shots_json_path.exists():
        print(f"未找到 shots.json：{shots_json_path}", file=sys.stderr)
        sys.exit(1)
    if not images_dir.exists():
        print(f"未找到 images 目录：{images_dir}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(shots_json_path.read_text(encoding="utf-8"))
    shots = sorted(data["shots"], key=lambda s: s["id"])
    if not shots:
        print("shots.json 中没有任何分镜", file=sys.stderr)
        sys.exit(1)

    timeline = build_timeline(shots)
    entries = [(find_image(images_dir, shot_id), duration) for shot_id, duration in timeline]

    # concat demuxer 的 `duration` 指令在混合总时长计算上不可靠（实测会显著跑偏），
    # 改用每张图片单独作为 -loop 输入并配 -t，再用 filter_complex concat 拼接，
    # 这样每段时长与 shots.json 完全对齐。
    cmd = ["ffmpeg", "-y"]
    for image_path, duration in entries:
        cmd += ["-loop", "1", "-t", f"{duration:.3f}", "-i", str(image_path)]

    filter_parts = []
    for i in range(len(entries)):
        filter_parts.append(f"[{i}:v]fps={args.fps},setsar=1[v{i}]")
    concat_inputs = "".join(f"[v{i}]" for i in range(len(entries)))
    filter_parts.append(f"{concat_inputs}concat=n={len(entries)}:v=1:a=0[outv]")
    filter_complex = ";".join(filter_parts)

    cmd += [
        "-filter_complex", filter_complex,
        "-map", "[outv]",
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]

    result = subprocess.run(
        cmd, capture_output=True, text=True, encoding="utf-8", errors="replace"
    )
    if result.returncode != 0:
        print(result.stderr, file=sys.stderr)
        sys.exit(1)

    total_duration = sum(d for _, d in entries)
    print(f"已生成视频：{output_path}（{len(entries)} 个分镜，总时长约 {total_duration:.2f} 秒）")


if __name__ == "__main__":
    main()
