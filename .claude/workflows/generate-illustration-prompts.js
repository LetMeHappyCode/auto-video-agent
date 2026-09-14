export const meta = {
  name: 'generate-illustration-prompts',
  description: '为每个镜头生成插画提示词并落盘，只向主智能体返回完成状态',
  phases: [
    { title: 'Load', detail: '读取 shots.json 并解析出 shots 数组' },
    { title: 'Generate', detail: '逐镜头生成插画提示词并由 agent 自行落盘' },
    { title: 'Verify', detail: '批量校验磁盘上的结果文件' },
  ],
}

// ============ Schema ============

// Load 阶段：只提取 shots.json 里下游需要的字段，不校验切分逻辑本身
const LOAD_SCHEMA = {
  type: 'object',
  properties: {
    source_srt: { type: 'string' },
    shots: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          id: { type: 'number' },
          start: { type: 'string' },
          end: { type: 'string' },
          text: { type: 'string' }
        },
        required: ['id', 'start', 'end', 'text']
      }
    }
  },
  required: ['source_srt', 'shots']
}

// prompt-generator 现在只回传极小状态对象，正文由它自己写入 result_path
const STATUS_SCHEMA = {
  type: 'object',
  properties: {
    shot_id: { type: 'number' },
    status: { type: 'string', enum: ['success', 'failed'] },
    result_path: { type: 'string' },
    error: { type: 'string' }
  },
  required: ['shot_id', 'status', 'result_path']
}

// 确保 output_dir 存在：由一次确定性调用完成，不依赖每个并发的 prompt-generator 各自判断
const DIR_SCHEMA = {
  type: 'object',
  properties: {
    ready: { type: 'boolean' },
    path: { type: 'string' },
    error: { type: 'string' }
  },
  required: ['ready', 'path']
}

const VERIFY_SCHEMA = {
  type: 'object',
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          shot_id: { type: 'number' },
          result_path: { type: 'string' },
          verified: { type: 'boolean' },
          error: { type: 'string' }
        },
        required: ['shot_id', 'result_path', 'verified']
      }
    }
  },
  required: ['results']
}

// ============ 输入 ============

const shotsPath = args.shots_path
const style = args.style
const protagonist = args.protagonist
const outputDir = args.output_dir

log('shots 文件：' + shotsPath)
log('画风：' + style)
log('主角：' + protagonist)
log('输出目录：' + outputDir)

// ============ Phase 0: 读取 shots.json（workflow 脚本本身无文件系统权限，交给 agent 读）============

phase('Load')

const loadPrompt = '用文件读取工具打开以下绝对路径，这是一份 srt-shot-segmenter 落盘的 JSON 文件（结构为 {source_srt, total_cues, total_shots, shots: [{id, start, end, text, source_srt_ids}, ...]}）。读取后原样提取 source_srt 字段，以及 shots 数组中每个元素的 id/start/end/text 四个字段（丢弃 source_srt_ids，下游不需要），按结构化输出返回，不得省略任何一个 shot，不得改写 text 内容。\n\n文件路径：\n' + shotsPath

const loaded = await agent(loadPrompt, {
  schema: LOAD_SCHEMA,
  phase: 'Load',
  label: 'Load shots.json'
})

if (!loaded || !loaded.shots || loaded.shots.length === 0) {
  return {
    source_srt: '',
    style: style,
    protagonist: protagonist,
    output_dir: outputDir,
    total_shots: 0,
    completed: 0,
    failed: 0,
    succeeded_shots: [],
    failed_shots: [],
    error: 'shots.json 读取失败或为空：' + shotsPath
  }
}

const shots = loaded.shots
const sourceSrt = loaded.source_srt

log('读取完成：' + shots.length + ' 个 shot')

// 构建完整文本（用于提供上下文）
let fullScript = ''
for (let i = 0; i < shots.length; i++) {
  fullScript += shots[i].text + ' '
}

// 提前算出每个 shot 的落盘路径，workflow 全程不读写这些文件本身
function resultPathFor(shotId) {
  const padded = String(shotId).padStart(4, '0')
  return outputDir + '/shot-' + padded + '.prompt.json'
}

// ============ 确保 output_dir 存在（一次性、确定性，不依赖每个并发 agent 各自判断）============

const dirPrompt = '用 Bash 执行 mkdir -p 创建以下目录（已存在也直接视为成功，不算错误）：\n\n' + outputDir + '\n\n创建或确认存在后，只返回结构化结果，不得输出其他内容。'

const dirResult = await agent(dirPrompt, {
  schema: DIR_SCHEMA,
  phase: 'Generate',
  label: 'Ensure output_dir'
})

if (!dirResult || !dirResult.ready) {
  return {
    source_srt: sourceSrt,
    style: style,
    protagonist: protagonist,
    output_dir: outputDir,
    total_shots: shots.length,
    completed: 0,
    failed: shots.length,
    succeeded_shots: [],
    failed_shots: [],
    error: 'output_dir 创建失败：' + (dirResult ? dirResult.error : 'agent returned null')
  }
}

// ============ Phase 1: 生成（agent 自行落盘，只回传状态）============

phase('Generate')

const genResults = await pipeline(
  shots,
  async (shot) => {
    const resultPath = resultPathFor(shot.id)

    const gp = '严格按你的 prompt-generator 协议，对以下单个 shot 执行一次全新、独立的 narrative-illustration-prompt 技能流程，并把完整结果原子写入 result_path。\n\nstyle（画风设定）：' + style + '\n\nprotagonist（主角设定）：' + protagonist + '\n\nfull_script（整篇长文案，仅用于理解上下文）：\n' + fullScript + '\n\nshot_text（当前目标片段，本次唯一处理对象，shot_id=' + shot.id + '）：\n' + shot.text + '\n\nresult_path（本次结果唯一允许写入的绝对路径）：\n' + resultPath + '\n\nshot_id 字段请填 ' + shot.id + '。不要参考或复用其他 shot 的分析与构图。你的最终回复只能是极小状态对象，不得包含 analysis 或 prompt 正文。'

    const r = await agent(gp, {
      schema: STATUS_SCHEMA,
      agentType: 'prompt-generator',
      phase: 'Generate',
      label: 'Shot ' + shot.id
    })

    if (!r) {
      return {
        shot_id: shot.id,
        shot_time: shot.start + ' --> ' + shot.end,
        result_path: resultPath,
        status: 'failed',
        error: 'agent returned null'
      }
    }

    return {
      shot_id: shot.id,
      shot_time: shot.start + ' --> ' + shot.end,
      result_path: r.result_path || resultPath,
      status: r.status,
      error: r.error || ''
    }
  }
)

let generatedOk = 0
let generatedFailed = 0
for (let i = 0; i < genResults.length; i++) {
  if (genResults[i].status === 'success') generatedOk++
  else generatedFailed++
}
log('生成阶段：' + generatedOk + ' 成功，' + generatedFailed + ' 失败（未落盘）')

// ============ Phase 2: 批量校验磁盘文件（脚本扫全目录，agent 只读问题项）============

phase('Verify')

const verifyPrompt = '请对 output_dir 下全部 shot 结果文件执行一次批量结构校验。\n\noutput_dir：\n' + outputDir + '\n\ntotal_shots：\n' + shots.length + '\n\n严格按你的协议：先调用 scripts/verify_shots.py 一次性扫描整个目录，只对脚本判定 verified=false 的条目做人工复核，不要逐个重新读取脚本已判定通过的文件。'

const verifyResult = await agent(verifyPrompt, {
  schema: VERIFY_SCHEMA,
  agentType: 'prompt-result-verifier',
  phase: 'Verify',
  label: 'Verify all'
})

let verifyMap = {}
if (verifyResult && verifyResult.results) {
  for (let i = 0; i < verifyResult.results.length; i++) {
    const v = verifyResult.results[i]
    verifyMap[v.shot_id] = v
  }
}

// ============ 汇总（不含任何 analysis / prompt 正文）============

const succeeded = []
const failed = []

for (let i = 0; i < genResults.length; i++) {
  const g = genResults[i]

  if (g.status !== 'success') {
    failed.push({ shot_id: g.shot_id, result_path: g.result_path, stage: 'generate', error: g.error })
    continue
  }

  const v = verifyMap[g.shot_id]
  if (!v) {
    failed.push({ shot_id: g.shot_id, result_path: g.result_path, stage: 'verify', error: 'not covered by verification pass' })
    continue
  }
  if (!v.verified) {
    failed.push({ shot_id: g.shot_id, result_path: g.result_path, stage: 'verify', error: v.error || 'verification failed' })
    continue
  }

  succeeded.push({ shot_id: g.shot_id, shot_time: g.shot_time, result_path: g.result_path })
}

log('校验阶段：' + succeeded.length + ' 通过，' + failed.length + ' 未通过')

// ============ 返回结果（极小，不含正文）============

return {
  source_srt: sourceSrt,
  style: style,
  protagonist: protagonist,
  output_dir: outputDir,
  total_shots: shots.length,
  completed: succeeded.length,
  failed: failed.length,
  succeeded_shots: succeeded,
  failed_shots: failed
}
