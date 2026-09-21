export const meta = {
  name: 'segment-srt-shots',
  description: '大文案先粗切为若干大段再精细分镜，最终产物仍是与单次切分完全一致的 shots.json',
  phases: [
    { title: 'Coarse', detail: '粗切 agent 只判断 cue 编号边界，不转录原文' },
    { title: 'Split', detail: '确定性代码按边界把原始 SRT 切成多份 segment SRT' },
    { title: 'Fine', detail: '逐段并发派发 srt-shot-segmenter 精细切分' },
    { title: 'Merge', detail: '确定性代码合并各段结果为最终 shots.json' },
  ],
}

// ============ Schema ============

const COARSE_STATUS_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['success', 'failed'] },
    result_path: { type: 'string' },
    total_cues: { type: 'number' },
    total_segments: { type: 'number' },
    error: { type: 'string' }
  },
  required: ['status', 'result_path']
}

const SPLIT_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    total_cues: { type: 'number' },
    segments: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          segment_id: { type: 'number' },
          cue_start: { type: 'number' },
          cue_end: { type: 'number' },
          cue_count: { type: 'number' },
          srt_path: { type: 'string' },
          time_start: { type: 'string' },
          time_end: { type: 'string' }
        },
        required: ['segment_id', 'cue_start', 'cue_end', 'srt_path']
      }
    },
    error: { type: 'string' }
  },
  required: ['ok']
}

const FINE_STATUS_SCHEMA = {
  type: 'object',
  properties: {
    status: { type: 'string', enum: ['success', 'failed'] },
    result_path: { type: 'string' },
    total_cues: { type: 'number' },
    total_shots: { type: 'number' },
    error: { type: 'string' }
  },
  required: ['status', 'result_path']
}

const MERGE_SCHEMA = {
  type: 'object',
  properties: {
    ok: { type: 'boolean' },
    result_path: { type: 'string' },
    total_cues: { type: 'number' },
    total_shots: { type: 'number' },
    error: { type: 'string' }
  },
  required: ['ok']
}

// ============ 输入 ============

const sourceSrt = args.source_srt
const resultPath = args.result_path
const targetSegmentCues = args.target_segment_cues || 40

log('源 SRT：' + sourceSrt)
log('最终输出：' + resultPath)

// shots.json.build/ 目录：与 result_path 同目录，存放粗切/精切中间产物
const buildDir = resultPath + '.build'
const coarsePath = buildDir + '/coarse.json'

// ============ Phase 0: 粗切（只判断边界，不转录原文）============

phase('Coarse')

const coarsePrompt = '请先用 Bash 执行 mkdir -p 创建以下目录（已存在也视为成功）：\n' + buildDir + '\n\n创建后，严格按你的协议对以下整份 SRT 执行粗切：\n\nsource_srt：\n' + sourceSrt + '\n\nresult_path：\n' + coarsePath + '\n\ntarget_segment_cues（每段期望 cue 数参考值）：\n' + targetSegmentCues

const coarseResult = await agent(coarsePrompt, {
  schema: COARSE_STATUS_SCHEMA,
  agentType: 'coarse-segmenter',
  phase: 'Coarse',
  label: 'Coarse segment boundaries'
})

if (!coarseResult || coarseResult.status !== 'success') {
  return {
    source_srt: sourceSrt,
    result_path: resultPath,
    total_cues: 0,
    total_shots: 0,
    error: '粗切失败：' + (coarseResult ? coarseResult.error : 'agent returned null')
  }
}

log('粗切完成：' + coarseResult.total_cues + ' cues，' + coarseResult.total_segments + ' 个大段')

// ============ Phase 1: 确定性代码切分原始 SRT（不经过 AI 转录）============

phase('Split')

const splitPrompt = '用 Bash 执行以下命令，只返回脚本打印的那一行 JSON 的结构化结果，不要自行解释或改写：\n\npython scripts/split_srt_by_coarse.py --source-srt "' + sourceSrt + '" --coarse "' + coarsePath + '" --out-dir "' + buildDir + '"'

const splitResult = await agent(splitPrompt, {
  schema: SPLIT_SCHEMA,
  phase: 'Split',
  label: 'Split SRT by coarse boundaries'
})

if (!splitResult || !splitResult.ok) {
  return {
    source_srt: sourceSrt,
    result_path: resultPath,
    total_cues: coarseResult.total_cues || 0,
    total_shots: 0,
    error: '确定性切分失败：' + (splitResult ? splitResult.error : 'agent returned null')
  }
}

const segments = splitResult.segments
log('切分完成：' + segments.length + ' 个 segment SRT 文件')

// ============ Phase 2: 逐段并发精细切分（复用现有 srt-shot-segmenter，输入只是变小的 SRT）============

phase('Fine')

function segmentResultPathFor(segmentId) {
  const padded = String(segmentId).padStart(4, '0')
  return buildDir + '/segment-' + padded + '.json'
}

const fineResults = await pipeline(
  segments,
  async (seg) => {
    const segResultPath = segmentResultPathFor(seg.segment_id)

    const fp = '严格按你的协议，对以下 SRT 文件执行一次性完整的六步法切分并落盘（这是原始大文案按场景边界切出的一个片段，cue 编号沿用原始全局编号，不是从 1 开始，按文件里实际写的 index 处理即可）。\n\nsource_srt：\n' + seg.srt_path + '\n\nresult_path：\n' + segResultPath

    const r = await agent(fp, {
      schema: FINE_STATUS_SCHEMA,
      agentType: 'srt-shot-segmenter',
      phase: 'Fine',
      label: 'Segment ' + seg.segment_id
    })

    if (!r) {
      return {
        segment_id: seg.segment_id,
        result_path: segResultPath,
        status: 'failed',
        error: 'agent returned null'
      }
    }

    return {
      segment_id: seg.segment_id,
      result_path: r.result_path || segResultPath,
      status: r.status,
      error: r.error || ''
    }
  }
)

let fineFailed = fineResults.filter((r) => r.status !== 'success')
if (fineFailed.length > 0) {
  return {
    source_srt: sourceSrt,
    result_path: resultPath,
    total_cues: coarseResult.total_cues || 0,
    total_shots: 0,
    error: '精细切分阶段有 ' + fineFailed.length + ' 个 segment 失败：' + JSON.stringify(fineFailed)
  }
}

log('精细切分完成：' + fineResults.length + ' 个 segment 全部成功')

// ============ Phase 3: 确定性代码合并为最终 shots.json ============

phase('Merge')

const orderedResultPaths = fineResults
  .slice()
  .sort((a, b) => a.segment_id - b.segment_id)
  .map((r) => r.result_path)

const segmentArgs = orderedResultPaths.map((p) => '--segment "' + p + '"').join(' ')

const mergePrompt = '用 Bash 执行以下命令，只返回脚本打印的那一行 JSON 的结构化结果，不要自行解释或改写：\n\npython scripts/merge_shots.py --source-srt "' + sourceSrt + '" --total-cues ' + coarseResult.total_cues + ' ' + segmentArgs + ' --result-path "' + resultPath + '"'

const mergeResult = await agent(mergePrompt, {
  schema: MERGE_SCHEMA,
  phase: 'Merge',
  label: 'Merge segment results into shots.json'
})

if (!mergeResult || !mergeResult.ok) {
  return {
    source_srt: sourceSrt,
    result_path: resultPath,
    total_cues: coarseResult.total_cues || 0,
    total_shots: 0,
    error: '合并失败：' + (mergeResult ? mergeResult.error : 'agent returned null')
  }
}

log('合并完成：' + mergeResult.total_shots + ' 个 shot 写入 ' + resultPath)

return {
  source_srt: sourceSrt,
  result_path: resultPath,
  total_cues: mergeResult.total_cues,
  total_shots: mergeResult.total_shots,
  error: ''
}
