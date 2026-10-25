# 数据契约

所有文件在 Life OS 的 `areas/relationship/`。Markdown 文件都带 Life OS 要求的 frontmatter（`name`、`description`、`aliases`、`updated`）。`anchor.py validate` 检查下面全部规则。

```
areas/relationship/README.md          主题总览（stated/inferred、当前状态、沿革）
areas/relationship/episodes.jsonl     一行一条真实事件，按 id 排序
areas/relationship/scenes/<id>.md     演练剧本，由 episode 生成
areas/relationship/views.md           见地库（含间隔复习状态）
areas/relationship/ladder.md          主体性阶梯（任务与完成记录）
areas/relationship/actions.md         「现在去做」清单
areas/relationship/drills.jsonl       演练记录
areas/relationship/drills/<date>.md   演练稿
areas/relationship/weekly/YYYY-WW.md  周复盘（ISO 周）
areas/relationship/inbox.md           只能写 Markdown 的客户端用的操作队列
areas/relationship/extraction/        历史素材的抽取报告与抽样核对
```

## episode

```json
{"id":"ep-2026-10-07-01","date":"2026-10-07","source_ref":"raw/conversations/2026-10/claude-….jsonl#<message id>",
 "trigger":"对方可观察的言行，原话或客观描述，不写动机",
 "my_thought":"我当时的原话，不改写",
 "body":"身体感受原话","urge":7,"certainty":80,
 "action":"checked|chased|held|said_ok|said_stop|said_no|other",
 "script_used":"好，你先休息。",
 "outcome":"happened|not_happened|unverifiable",
 "outcome_fact":"只记可观察事实；对方的解释不算",
 "recovery_minutes":40,"suds_peak":80,
 "miss":false,"miss_conditions":["半夜","电话","刚见完面"],
 "notes":""}
```

- `id` = `ep-<date>-<两位序号>`，日期与 `date` 一致；`date` 是事件发生日（Asia/Singapore）。
- 未知值：数字和 `action`/`outcome`/`miss` 用 `null`，文本用 `""`，条件用 `[]`。`outcome` 为 `null` 表示待回填。
- `urge` 0–10，`certainty`/`suds_peak` 0–100，`recovery_minutes` 非负整数。
- `outcome` 为 `happened`/`not_happened` 时 `outcome_fact` 必填；事实看起来是对方的解释时给出警告，`/fact` 默认改记 `unverifiable`。
- `miss=true` 必须有 `action`。
- 可选扩展字段：`recorded_at`（带时区的记录时刻，用于 24–72 小时追问）、`origin`（`now`/`export`/`capture`/`inbox`/`manual`）、`review`（历史抽取的核对状态：`pending` 待核对、`accepted` 批次经本人抽样验收但未逐条核对、`confirmed` 本人逐条确认、`rejected` 本人否掉）。不允许其他字段。
- 历史抽取的 `my_thought`、`body` 必须是 `source_ref` 那条本人消息的逐字片段（忽略空白，可用 `…` 连接同一消息里的几段），`anchor.py extract verify` 检查。

## scene

```markdown
---
name: 演练剧本 sc-2026-10-07-01
description: …
aliases: [sc-2026-10-07-01]
updated: 2026-10-25
scene: sc-2026-10-07-01
episode: ep-2026-10-07-01
suds_expected: 60
script: 好，你先休息。
cue: 我想自己待一会。
conditions: [半夜, 电话]
---

# sc-2026-10-07-01

来源 ep-2026-10-07-01｜预期 SUDS 60｜练这一句：「好，你先休息。」

## 剧本

（第一人称、现在时、本人原话、带身体感受，不超过 150 字，不算空白）

## 对方那句话

「我想自己待一会。」
```

`cue` 是演练时由"对方"说出的那句话。`conditions` 用于按 miss 条件加权选题和轮换渠道（文字/电话/当面）。

## views.md

```markdown
- **V01** 一句话见地。
  - 出处：[stated] 「本人原话」— raw/conversations/….jsonl#<message id>（2026-01-15）
  - 复习：阶段 0（间隔 1 天）｜下次 2026-10-26｜上次 —
```

`[stated]` 必须带「原话」和 `raw/` 出处；`[inferred]` 必须写借用来源（书名用《》）。复习间隔 1/3/7/14/30 天：阶段 s 复习成功后按「间隔」排下一次，阶段加一；`--again` 回到阶段 0、明天再来。

## ladder.md

```markdown
- [ ] **L01**｜关系外｜点餐时说一次「不要 X」，不解释原因。
  - 2026-10-27 完成｜SUDS 30｜备注
```

区域写「关系外」或「关系内」。完成两次且最近一次 SUDS ≤ 40 自动打勾；本人手动打勾同样算完成。

## actions.md

`## 事业`、`## 健康`、`## 社交` 三个标题下的列表项，每项是十几分钟内能开始的具体动作。

## drills.jsonl

```json
{"id":"dr-2026-10-26-01","date":"2026-10-26","scene":"sc-…","view":"V03","hot":false,
 "suds_before":60,"suds_after":35,"within_3s":true,"verbatim":true,"held_30s":true,"notes":""}
```

## inbox.md 操作

代码块 ```` ```jsonl ```` 里每行一个操作，按顺序执行：

```json
{"op":"episode","date":"2026-10-26","source_ref":"live:claude-ai:<会话标题或 id>","trigger":"…","my_thought":"…","body":"…","certainty":70,"urge":8,"script_used":"好，你先休息。","miss_conditions":["半夜"],"recorded_at":"2026-10-26T23:10:00+08:00"}
{"op":"fact","id":"ep-2026-10-26-01","outcome":"not_happened","outcome_fact":"第二天中午她约我吃饭","recovery_minutes":40}
{"op":"drill","date":"2026-10-26","scene":"sc-…","view":"V03","suds_before":60,"suds_after":35,"within_3s":true,"verbatim":true,"held_30s":true}
{"op":"ladder","id":"L01","suds":30,"date":"2026-10-27","note":""}
{"op":"view","id":"V03","date":"2026-10-26","remembered":true}
{"op":"review","id":"ep-2026-08-25-03","status":"confirmed","note":""}
```

- `episode` 可以不带 `id`（合并时分配）；带了但与已有记录冲突时自动换号，同一批后续 `fact` 跟着改号。与已有记录完全相同的视为重复。
- `fact` 的 `observed: true` 对应 `/fact --observed`。
- 合并后成功的行被移除，失败的行留在队列里并报告原因；每执行一行就重写一次队列，中断后重跑不会重复执行。
