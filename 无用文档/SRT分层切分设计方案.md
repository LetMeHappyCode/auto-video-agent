# SRT 分层切分设计方案

## 设计目标

针对大型 SRT 字幕文件，通过分层处理避免单次 AI 调用处理过多内容导致的质量下降问题，同时保证每个切分单元都严格执行完整的 srt-shots 技能流程。

## 核心参数

- **segment_size**: 50 条 cue（每个切分单元的大小）
- **overlap**: 6 条 cue（相邻单元的重叠边界）
- **技能约束**: 每个切分单元必须完整执行 srt-shots 的六步法流程

## 四阶段架构

### Phase 1: 确定性预切分（Presegment）

**职责**: 使用 Python 脚本按固定规则将 SRT 文件切分为多个 segment，保留重叠边界。

**输入**:
- `srt_path`: 原始 SRT 文件的绝对路径
- `segment_size`: 50
- `overlap`: 6

**输出**: `segments.json`

```json
{
  "source_srt": "example.srt",
  "total_cues": 237,
  "segments": [
    {
      "segment_id": 1,
      "cues": [
        {"id": 1, "start": "00:00:00,000", "end": "00:00:03,500", "text": "..."},
        {"id": 2, "start": "00:00:03,500", "end": "00:00:06,200", "text": "..."}
      ],
      "start_cue_id": 1,
      "end_cue_id": 50,
      "has_overlap_next": true
    },
    {
      "segment_id": 2,
      "cues": [
        {"id": 45, "start": "00:02:30,000", "end": "00:02:33,000", "text": "..."},
        {"id": 46, "start": "00:02:33,000", "end": "00:02:36,500", "text": "..."}
      ],
      "start_cue_id": 45,
      "end_cue_id": 94,
      "has_overlap_next": true
    }
  ]
}
```

**切分逻辑**:
```python
# 伪代码
for i in range(0, len(cues), segment_size - overlap):
    chunk = cues[i : i + segment_size]
    segments.append({
        'segment_id': len(segments) + 1,
        'cues': chunk,
        'start_cue_id': chunk[0]['id'],
        'end_cue_id': chunk[-1]['id'],
        'has_overlap_next': i + segment_size < len(cues)
    })
```

**重叠目的**: 
- 让相邻 segment 有 6 条 cue 的共同上下文
- 边界修复时能看到完整的跨段事件
- 避免在场景中间生硬切断

---

### Phase 2: 并行切分（Segment Chunks）

**职责**: 对每个 segment 独立派发 `srt-shot-segmenter` agent，完整执行 srt-shots 技能的六步法。

**并发模式**: 使用 `pipeline()` 流式处理各个 segment，引擎自动控制并发上限。

**输入**: 
- 每个 segment 的 cues 数组
- srt-shots 技能的完整执行要求

**输出**: `segment-{id}.shots.json`（每个 segment 一个）

```json
{
  "segment_id": 1,
  "source_segment": {
    "start_cue_id": 1,
    "end_cue_id": 50
  },
  "shots": [
    {
      "id": 1,
      "start": "00:00:00,000",
      "end": "00:00:08,500",
      "text": "合并后的自然语言字幕文案",
      "source_srt_ids": [1, 2, 3]
    },
    {
      "id": 2,
      "start": "00:00:08,500",
      "end": "00:00:15,200",
      "text": "第二个镜头的文案",
      "source_srt_ids": [4, 5, 6, 7]
    }
  ],
  "stats": {
    "total_cues": 50,
    "total_shots": 12
  }
}
```

**技能执行约束**:

每个 agent 必须严格执行以下六步：

1. **解析验证**: 校验时间戳格式、顺序，遇到格式错误立即停止
2. **动词名词扫描**: 标记行为动词和环境名词，识别位置转换和核心动作切换
3. **Cue 分类**: 区分核心叙事、修饰描述、铺垫/说明
4. **三不原则应用**: 
   - 合并：共享位置/动作、微动作、抽象情绪配物理动作
   - 切分：新位置、新时间、独立核心动作、自足情绪节拍
5. **密度压缩**: 目标 2-6 秒/shot，单条 >6 秒保持完整并标记
6. **交叉检查**: 确保每个 cue 恰好出现一次，无遗漏、无重复、无乱序

**Agent Prompt 模板**:

```
你是 srt-shot-segmenter，负责对以下 {cue_count} 条字幕执行完整的 srt-shots 切分流程。

严格执行六步法：
1. 解析验证所有时间戳和顺序
2. 扫描所有动词和名词，标记场景切换点
3. 对每条 cue 分类（核心叙事/修饰/铺垫）
4. 应用三不原则决定合并或切分
5. 压缩密度，目标 2-6 秒/shot
6. 交叉检查覆盖完整性

输入字幕：
[1] 00:00:00,000 --> 00:00:03,500
第一条字幕内容

[2] 00:00:03,500 --> 00:00:06,200
第二条字幕内容

...

输出 JSON Schema:
{
  "shots": [
    {
      "id": number (从 1 开始连续),
      "start": "HH:MM:SS,mmm",
      "end": "HH:MM:SS,mmm",
      "text": "合并后的连续自然语言文案（相邻 cue 之间用半角空格连接）",
      "source_srt_ids": [整数数组]
    }
  ]
}

约束：
- 每个输入 cue 必须恰好出现在一个 shot 的 source_srt_ids 中
- shot.id 必须从 1 开始连续递增
- start/end 严格保持 HH:MM:SS,mmm 格式（逗号分隔毫秒）
- text 中不得包含 Markdown 表格分隔符 |
```

**质量保证**:
- 每个 agent 只处理 50 条 cue，注意力集中
- 技能流程在每个 segment 内完整执行，不打折扣
- schema 强制输出符合规范，格式错误直接失败

---

### Phase 3: 边界修复（Fix Boundaries）

**职责**: 检查相邻 segment 的边界 shot，判断是否应该合并跨段的镜头。

**输入**: 
- 所有 segment 的 shots 结果
- 每对相邻 segment 的边界 shots（当前段末尾 2 个 + 下一段开头 2 个）

**输出**: `boundaries.json`

```json
{
  "decisions": [
    {
      "boundary_index": 0,
      "segment_pair": [1, 2],
      "current_last_shots": [
        {"id": 11, "text": "...", "source_srt_ids": [45, 46, 47]},
        {"id": 12, "text": "...", "source_srt_ids": [48, 49, 50]}
      ],
      "next_first_shots": [
        {"id": 1, "text": "...", "source_srt_ids": [45, 46, 47, 48]},
        {"id": 2, "text": "...", "source_srt_ids": [49, 50, 51]}
      ],
      "decision": {
        "action": "merge",
        "reason": "末尾 shot 和开头 shot 的 source_srt_ids 有重叠（45-50），且描述同一场景的连续动作"
      }
    },
    {
      "boundary_index": 1,
      "segment_pair": [2, 3],
      "current_last_shots": [...],
      "next_first_shots": [...],
      "decision": {
        "action": "keep",
        "reason": "明显的场景切换，从室内对话转到室外街景"
      }
    }
  ]
}
```

**判断规则**:

针对每对相邻 segment 的边界：

1. **重叠检测**: 检查末尾 shot 和开头 shot 的 `source_srt_ids` 是否有交集
   - 有交集 → 大概率应该合并（因为它们处理了相同的 cue）
   - 无交集 → 检查语义连续性

2. **语义判断**: 
   - 同一地点？同一核心动作？ → 合并
   - 独立事件？场景切换？ → 保持分离

3. **三不原则复核**: 对边界应用 srt-shots 的三不原则
   - 符合"合并条件" → merge
   - 符合"切分条件" → keep

**Agent Prompt 模板**:

```
你是边界修复专家，负责判断相邻两个 segment 的边界是否需要合并。

当前段末尾镜头（最后 2 个）：
{json_of_last_shots}

下一段开头镜头（前 2 个）：
{json_of_first_shots}

判断规则：
1. 检查 source_srt_ids 是否有重叠（重叠意味着两个 agent 处理了相同的 cue，需要合并去重）
2. 判断是否属于同一地点、同一核心动作
3. 应用 srt-shots 的三不原则：
   - 合并条件：共享位置/动作、微动作延续、情绪与动作一体
   - 切分条件：新位置、新时间、独立核心动作、场景明显切换

输出 JSON Schema:
{
  "action": "merge" | "keep",
  "reason": "详细说明判断依据，包括是否有 source_srt_ids 重叠、场景是否连续、动作是否一致"
}
```

**并发模式**: `pipeline()` 处理所有边界对，每对独立判断。

---

### Phase 4: 确定性合并（Merge）

**职责**: 根据边界修复决策，将所有 segment 的 shots 合并为最终的 `shots.json`，并执行全局校验。

**输入**:
- 所有 `segment-{id}.shots.json`
- `boundaries.json`
- 原始 SRT 的 total_cues

**输出**: `shots.json`（最终结果）

```json
{
  "version": 1,
  "source_srt": "example.srt",
  "total_cues": 237,
  "total_shots": 58,
  "shots": [
    {
      "id": 1,
      "start": "00:00:00,000",
      "end": "00:00:08,500",
      "text": "合并后的自然语言字幕文案",
      "source_srt_ids": [1, 2, 3]
    },
    {
      "id": 2,
      "start": "00:00:08,500",
      "end": "00:00:15,200",
      "text": "第二个镜头的文案",
      "source_srt_ids": [4, 5, 6, 7]
    }
  ]
}
```

**合并逻辑** (Python 脚本):

```python
def merge_segments(segment_results, boundary_decisions, total_cues):
    all_shots = []
    skip_next_first = set()  # 记录因合并而需要跳过的 shot
    
    for i, segment_result in enumerate(segment_results):
        shots = segment_result['shots']
        
        # 检查是否需要跳过第一个 shot（因为被前一段合并了）
        if i in skip_next_first:
            shots = shots[1:]
        
        # 检查当前段末尾是否需要与下一段开头合并
        if i < len(boundary_decisions):
            decision = boundary_decisions[i]['decision']
            
            if decision['action'] == 'merge':
                last_shot = shots[-1]
                next_first_shot = segment_results[i + 1]['shots'][0]
                
                # 合并逻辑
                merged_shot = {
                    'start': last_shot['start'],
                    'end': next_first_shot['end'],
                    'text': merge_text(last_shot['text'], next_first_shot['text']),
                    'source_srt_ids': merge_and_deduplicate(
                        last_shot['source_srt_ids'],
                        next_first_shot['source_srt_ids']
                    )
                }
                shots[-1] = merged_shot
                skip_next_first.add(i + 1)
        
        all_shots.extend(shots)
    
    # 重新分配全局连续 id
    for idx, shot in enumerate(all_shots, start=1):
        shot['id'] = idx
    
    # 全局校验
    validate_final_shots(all_shots, total_cues)
    
    return all_shots

def merge_text(text1, text2):
    """合并两段文本，去重重叠部分"""
    # 如果 text2 的开头部分与 text1 的结尾重叠，去重
    # 否则用半角空格连接
    # 实现细节略
    pass

def merge_and_deduplicate(ids1, ids2):
    """合并两个 source_srt_ids 数组并去重"""
    return sorted(set(ids1 + ids2))

def validate_final_shots(shots, total_cues):
    """全局校验"""
    # 1. 收集所有 source_srt_ids
    all_ids = []
    for shot in shots:
        all_ids.extend(shot['source_srt_ids'])
    
    # 2. 检查是否覆盖全部 cue 且无重复
    if sorted(all_ids) != list(range(1, total_cues + 1)):
        raise ValueError("shots 未完整覆盖所有 cue 或存在重复")
    
    # 3. 检查时间连续性
    for i in range(len(shots) - 1):
        if shots[i]['end'] != shots[i + 1]['start']:
            raise ValueError(f"shot {shots[i]['id']} 和 {shots[i+1]['id']} 时间不连续")
    
    # 4. 检查 id 连续性
    for i, shot in enumerate(shots, start=1):
        if shot['id'] != i:
            raise ValueError(f"shot id 不连续，期望 {i}，实际 {shot['id']}")
    
    return True
```

**校验项**:

1. **完整覆盖**: 所有 source_srt_ids 排序后应该是 `[1, 2, 3, ..., total_cues]`
2. **无重复**: 每个 cue id 只能出现一次
3. **时间连续**: 相邻 shot 的 end 和 start 必须相等（无缝衔接）
4. **ID 连续**: 最终 shot.id 必须从 1 开始连续递增
5. **格式规范**: 时间戳格式、text 无非法字符

**错误处理**:
- 任何校验失败都立即抛出异常，停止合并
- 不尝试"修补"数据，而是报告具体错误位置让上游修复

---

## Workflow 实现概要

```javascript
export const meta = {
  name: 'srt-hierarchical-segmentation',
  description: 'SRT 分层切分为语义镜头',
  phases: [
    { title: 'Presegment', detail: '确定性预切分（50 cue/段，6 cue 重叠）' },
    { title: 'Segment chunks', detail: '并行执行完整 srt-shots 技能' },
    { title: 'Fix boundaries', detail: '修复跨段边界镜头' },
    { title: 'Merge', detail: '确定性合并并全局校验' },
  ],
}

// === Phase 1: Presegment ===
phase('Presegment')
log('开始预切分 SRT 文件，segment_size=50，overlap=6')

const presegmentResult = await execute_bash(`
  python scripts/presegment_srt.py \\
    --srt "${srtPath}" \\
    --segment-size 50 \\
    --overlap 6 \\
    --output segments.json
`)

const segments = JSON.parse(read('segments.json'))
log(`预切分完成：${segments.segments.length} 个 segment，共 ${segments.total_cues} 条 cue`)

// === Phase 2: Segment chunks ===
phase('Segment chunks')
log(`开始并行切分 ${segments.segments.length} 个 segment`)

const segmentResults = await pipeline(
  segments.segments,
  async (segment) => {
    const prompt = buildSegmentPrompt(segment)
    const result = await agent(prompt, {
      schema: SHOTS_SCHEMA,
      agentType: 'srt-shot-segmenter',
      phase: 'Segment chunks',
      label: `Segment ${segment.segment_id}`
    })
    
    // 持久化每个 segment 的结果
    write(`segment-${segment.segment_id}.shots.json`, JSON.stringify(result, null, 2))
    
    return {
      segment_id: segment.segment_id,
      shots: result.shots,
      source_segment: {
        start_cue_id: segment.start_cue_id,
        end_cue_id: segment.end_cue_id
      }
    }
  }
)

log(`切分完成：共生成 ${segmentResults.map(r => r.shots.length).reduce((a,b) => a+b, 0)} 个初步 shot`)

// === Phase 3: Fix boundaries ===
phase('Fix boundaries')
log(`开始修复 ${segmentResults.length - 1} 个边界`)

const boundaryDecisions = await pipeline(
  range(segmentResults.length - 1),
  async (i) => {
    const currentLast = segmentResults[i].shots.slice(-2)
    const nextFirst = segmentResults[i + 1].shots.slice(0, 2)
    
    const decision = await agent(buildBoundaryPrompt(currentLast, nextFirst), {
      schema: BOUNDARY_DECISION_SCHEMA,
      phase: 'Fix boundaries',
      label: `Boundary ${i}-${i+1}`
    })
    
    return {
      boundary_index: i,
      segment_pair: [segmentResults[i].segment_id, segmentResults[i + 1].segment_id],
      current_last_shots: currentLast,
      next_first_shots: nextFirst,
      decision: decision
    }
  }
)

write('boundaries.json', JSON.stringify({ decisions: boundaryDecisions }, null, 2))
log(`边界修复完成：${boundaryDecisions.filter(d => d.decision.action === 'merge').length} 个合并，${boundaryDecisions.filter(d => d.decision.action === 'keep').length} 个保持`)

// === Phase 4: Merge ===
phase('Merge')
log('开始确定性合并并全局校验')

const mergeResult = await execute_bash(`
  python scripts/merge_segments.py \\
    --segments segment-*.shots.json \\
    --boundaries boundaries.json \\
    --total-cues ${segments.total_cues} \\
    --output shots.json
`)

const finalShots = JSON.parse(read('shots.json'))
log(`合并完成：最终 ${finalShots.total_shots} 个 shot，覆盖 ${finalShots.total_cues} 条 cue`)

return {
  output_path: resolve('shots.json'),
  total_cues: finalShots.total_cues,
  total_shots: finalShots.total_shots,
  segments_processed: segments.segments.length
}
```

---

## 关键优势

### 1. 质量稳定性
- 每个 agent 只处理 50 条 cue，注意力集中，不会衰减
- 技能流程（六步法）在每个 segment 内完整执行，不打折扣

### 2. 并行度高
- 所有 segment 可以同时切分（受引擎并发上限自动控制）
- 墙上时间 ≈ 单个 segment 的处理时间（而非总时间）

### 3. 边界问题显式处理
- 不依赖"AI 自己注意跨段一致性"
- 用专门的边界修复 agent 只做"该不该合并"这一件事
- 重叠 6 条 cue 保证边界有足够上下文

### 4. 确定性保证
- 预切分和合并都用 Python 脚本（确定性逻辑）
- 合并阶段做严格的全局校验（覆盖、去重、连续性）
- 任何校验失败都立即报错，不输出脏数据

### 5. 可追溯性
- 每个 segment 的结果都持久化为独立文件
- 边界决策单独保存，可人工审查
- 最终 shot 的 source_srt_ids 可回溯到原始 cue

---

## 参数调优指南

### segment_size（当前 50）
- **太小（<30）**: 
  - 丢失上下文，场景理解不完整
  - segment 数量多，边界修复工作量大
  - 并发度虽高但单个质量下降
  
- **太大（>80）**: 
  - 接近原问题，注意力衰减
  - 并行度降低（大文件只能切成少数几段）
  
- **推荐范围**: 40-60 条 cue

### overlap（当前 6）
- **太小（<3）**: 
  - 边界上下文不足，修复判断困难
  - 容易在句子中间生硬切断
  
- **太大（>10）**: 
  - 重复处理过多，浪费 token
  - 边界修复时重叠部分过长，难以判断
  
- **推荐范围**: 5-8 条 cue

### 边界检查范围（当前末尾 2 + 开头 2）
- 可根据实际调整为 1+1 或 3+3
- 1+1: 快速但可能漏判复杂边界
- 3+3: 更谨慎但 prompt 更长

---

## 错误处理策略

### Presegment 阶段
- SRT 格式错误 → 立即停止，报告错误位置
- 文件过小（<20 cue） → 警告但继续，直接作为单 segment

### Segment chunks 阶段
- 单个 segment 切分失败 → 记录失败，继续处理其他 segment
- schema 校验失败 → 重试 1 次，仍失败则标记该 segment 失败
- 最终如果失败 segment 超过 20% → 停止整个流程

### Fix boundaries 阶段
- 边界判断失败 → 默认为 "keep"（保守策略，避免错误合并）
- 多次失败 → 人工介入检查

### Merge 阶段
- 校验失败（覆盖、重复、连续性） → 立即停止，报告详细错误
- 不尝试自动修复，而是要求重新执行上游阶段

---

## 后续扩展方向

### 1. 自适应 segment_size
根据 SRT 的 cue 密度（平均每条 cue 的时长）动态调整 segment_size：
- 短 cue（<2 秒）→ 增大 segment_size
- 长 cue（>5 秒）→ 减小 segment_size

### 2. 边界置信度
让边界修复 agent 返回置信度分数，低置信度边界标记为"需人工审查"

### 3. 增量更新
当 SRT 内容变化时，只重新处理受影响的 segment，复用未变化部分

### 4. 质量评分
对每个 segment 的切分结果评分（基于密度分布、时长方差等），低分段自动重试

---

## 文件结构

```
project/
├── scripts/
│   ├── presegment_srt.py          # Phase 1: 预切分脚本
│   └── merge_segments.py          # Phase 4: 合并脚本
├── .claude/
│   ├── agents/
│   │   ├── srt-shot-segmenter.md  # Phase 2: 切分 agent 定义
│   │   └── boundary-fixer.md      # Phase 3: 边界修复 agent 定义
│   └── workflows/
│       └── srt-hierarchical-segmentation.js  # 主 workflow 脚本
└── data/
    ├── example.srt                 # 输入
    ├── segments.json               # Phase 1 输出
    ├── segment-1.shots.json        # Phase 2 输出
    ├── segment-2.shots.json
    ├── ...
    ├── boundaries.json             # Phase 3 输出
    └── shots.json                  # Phase 4 最终输出
```

---

## 总结

这套分层切分方案通过"确定性预切分 + 并行独立处理 + 专门边界修复 + 确定性合并"四阶段架构，在保证每个切分单元都严格执行完整技能流程的前提下，解决了大型 SRT 文件的质量和效率问题。

核心思想：**让 AI 专注做它擅长的语义理解和判断，让确定性代码负责数据流转和校验**。
