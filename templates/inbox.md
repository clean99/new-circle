---
name: 抛锚训练待合并队列
description: MCP 客户端写入的 episode、事实回填、演练与阶梯记录，待本地脚本合并。
aliases: [anchor inbox, 抛锚队列]
updated: 2026-01-01
---

# 抛锚训练待合并队列

能读写 Markdown、但不能直接写 `episodes.jsonl` 的客户端（Claude.ai 经 life-os MCP、其他 bot）把操作追加到下面的代码块里，每行一个 JSON。本地运行 `anchor.py ingest` 时按顺序合并进正式数据，成功的行会被移除，失败的行保留并在终端报告原因。

格式见 anchor-training 技能的 `references/data-contract.md`。不要在这里写正文分析。

```jsonl
```
