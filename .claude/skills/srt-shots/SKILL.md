---
name: srt-shots
description: Turn SRT video subtitles into structured storyboard semantic blocks (分镜语义块) using the 三不原则 and 四步法. Use when the user provides an SRT file or timestamped SRT text and asks for 分镜、shots、storyboard、镜头语义块、故事节奏切分 or 语义连贯度切分. Do not use for subtitle translation, speech-to-text/SRT generation, or downstream image/video prompt generation.
---

# SRT Shots

Split subtitles into merged, paced semantic blocks so each block contains one visual core and can be used as precise input for downstream prompt generation.

## Input and output

- Read an SRT file path or pasted SRT-formatted text with `HH:MM:SS,mmm --> HH:MM:SS,mmm` timestamps.
- Preserve cue order and original wording. If a downstream consumer is named, tune only the event-summary wording toward image or video needs.
- Output a 1–4 line preamble stating total cues, total blocks, and anomalies, followed by this table:

| 分镜编号 | 时间轴区间 | 合并后的文案语义块 | 核心事件概括 |
|---|---|---|---|

Use zero-padded sequential IDs (`01`, `02`, ...). Use the first cue start and last cue end for each range. Concatenate cue text naturally without paraphrasing. Make `核心事件概括` exactly one sentence describing one visual core.

## Procedure

1. **Parse and validate.** Extract `[index, start, end, text]`, skip blank cues, preserve order, and stop with malformed cue indices if timestamps are missing or out of order. Do not guess. Reject VTT, ASS, or TTML unless the user confirms conversion.
2. **Scan verbs and nouns.** Read all subtitles first. Mark behavior verbs and environment nouns; treat every location transition or core-action switch as a candidate split.
3. **Classify cues.** Mark each cue as core narrative, modifier description, or exposition/setup. Attach modifiers to the nearest core action. Attach setup to the first action block unless it clearly stands alone.
4. **Apply 三不原则.** Merge cues when they share a location/action, when one is a micro-action, or when an abstract emotion belongs beside a physical action. Split on a new location, time, independent core action, or self-contained emotional beat.
5. **Compress by density.** Aim for 2–6 seconds per block. Keep a single cue longer than 6 seconds intact and flag it. Split any block that cannot be summarized in one sentence. Merge adjacent blocks with duplicate core events.
6. **Render and cross-check.** Ensure every cue appears exactly once, block ranges have no gaps or overlaps, every summary is one sentence, and adjacent summaries are not identical. A single-block result is valid; note `single scene`.

## Failure handling

- Malformed timestamps or ordering: report the affected cue indices and stop.
- Long single cue: keep intact and flag in the preamble; never auto-split.
- Fewer than five cues: apply the same SOP without special reduction.

No shell commands, scripts, or Python are needed; perform the segmentation directly from the supplied SRT.
