# 历史素材的导入与抽取

## 1. 导入原文（用 Life OS 自带的导入器，不重写）

Claude 网页 Settings → Privacy → Export data。收到的是下载清单 JSON 和若干 ZIP（`conversations-000.zip` 是聊天正文）。把 ZIP 按清单里的文件名放进一个空目录（浏览器给重名文件加的 ` (1)` 要去掉），然后在 Life OS 根目录：

```bash
python3 scripts/import_claude_export.py --manifest <清单> --download-dir <目录> --inventory-only
python3 scripts/import_claude_export.py --manifest <清单> --download-dir <目录> \
  --import-category conversations --import-category projects --import-category memories \
  --import-category design_chats --import-category frames
```

导入器按消息稳定标识去重：重复导出只追加新消息。它按会话判断覆盖：有被排除的隐藏块或缺附件的会话标 `partial`，其余标 `full_export`。清单含临时下载链接，不进仓库。一次导入作为一次提交：`capture: Claude 官方导出 <日期> 增量归档`。

## 2. 关键词初筛 → 分片

```bash
python3 <本技能>/scripts/anchor.py --repo <Life OS> extract candidates --out /tmp/anchor-shards --min-hits 2
```

只看本人消息（`role=user`），对每段对话计关键词命中；命中 ≥ 2 条（或很短的对话命中 1 条）的进入候选。分片阅读稿里本人消息全文保留、标出 `ref=<raw 文件>#<消息 id>`，助手回复只留前 240 字作上下文。

## 3. LLM 分类与抽取

每个分片交给一个 agent，按统一规范输出 episodes / views / scenes 候选（规范要点：只用本人原话；对方只记可观察言行；不推断任何人的动机；数字只在本人明确给出时填写；对方的解释记 unverifiable）。并发不超过 4 个，完整结果落盘，回报只给路径和计数。

## 4. 逐字核对、去重、编号

```bash
python3 <本技能>/scripts/anchor.py --repo <Life OS> extract verify <候选.jsonl>
```

`my_thought`、`body` 不是 `source_ref` 那条本人消息的逐字片段就作废；引用到助手消息也作废。同一事件只留最早、最完整的那条，按日期分配 `ep-<date>-NN`，`origin: export`、`review: pending`。

## 5. 交本人核对

```bash
python3 <本技能>/scripts/anchor.py --repo <Life OS> extract sample --n 20 --seed <seed> \
  --out areas/relationship/extraction/<date>-sample.md
```

随机 20 条与原文并排，本人逐条打勾或写「错：……」。核对完把对应 episode 的 `review` 改成 `confirmed`/`rejected`；错误率高就回到第 3 步改规范重跑。
