# 三处运行与安装

## Claude Code（直接改仓库）

安装（用户级技能，和其他技能一样放在 `~/.codex/skills/` 再链接给 Claude Code）：

```bash
git clone https://github.com/clean99/new-circle.git ~/new-circle
ln -sfn ~/new-circle ~/.codex/skills/anchor-training
ln -sfn ~/.codex/skills/anchor-training ~/.claude/skills/anchor-training
```

`anchor.py` 按顺序找 Life OS：`--repo` → `$LIFE_OS_REPO` → `~/.claude/skills/life-os/references/location.json`（life-os 安装器写入的 `knowledge_root`）→ `~/.agents/skills/life-os/references/location.json`。第一次用新仓库时运行 `anchor.py init`，只创建缺失的文件。

写入纪律（Life OS 规则）：

1. 写之前先 `git -C <Life OS> pull --rebase`。
2. 每次独立写入单独提交：`anchor.py commit -m "fact: areas/relationship 记录 ep-…"`（只提交 `areas/relationship/`）。
3. `git push`；拿到提交号才算保存成功。
4. 有 MCP 客户端在用时，先 `anchor.py ingest` 合并 `inbox.md`，再做别的写入。

## Claude.ai（经 life-os MCP 读写）

上传技能：在本仓库运行 `make package`，把 `dist/anchor-training.zip` 在 Claude.ai 的 Settings → Capabilities → Skills 上传。life-os 连接器需已连上（`get_context` 能返回）。

读取：`read` 可以读 `areas/relationship/` 下所有文件，包括 `episodes.jsonl`、`drills.jsonl`。

写入：life-os MCP 只允许 `update_note` 写 `.md`，不能直接写 jsonl。所以：

- `/now`、`/fact`、演练记录、阶梯完成、见地复习、`/review` 核对 → 读 `areas/relationship/inbox.md`（拿 sha）→ 在 ```` ```jsonl ```` 代码块末尾追加一行操作（格式见 [data-contract.md](data-contract.md#inboxmd-操作)）→ `update_note`（`expected_sha` 用刚读到的，`name`/`description` 保持原值）。冲突就重读再追加，最多 3 次。
- 新 episode 的 `id`：读 `episodes.jsonl` 和 `inbox.md`，取当天未用的最小序号；不确定就不带 `id`，合并时分配。`/fact` 引用尚在队列里的 episode 时直接用它的 `id`。
- `/weekly`：如果有代码执行环境，把 `episodes.jsonl`、`drills.jsonl`、`views.md`、`ladder.md` 和队列内容读出来，在沙盒里建一个最小目录（`AGENTS.md`、`raw/`、`areas/relationship/…`），运行 `python3 scripts/anchor.py --repo <沙盒> ingest` 和 `weekly`，再把结果用 `update_note` 写到 `areas/relationship/weekly/YYYY-WW.md`。没有代码执行时按 [protocols.md#weekly](protocols.md#weekly) 的定义手算，并在周报里注明"手算"。
- `/drill`：读 `scenes/`、`drills.jsonl`、`views.md`，按 [protocols.md#drill](protocols.md#drill) 选题；或直接用 `drills/` 里预生成的当天演练稿。语音模式下由 bot 说出 cue。
- 本地 Claude Code 下次运行任何命令前先 `anchor.py ingest`，把队列合并进正式数据并提交。

## Grok Bot 与其他 agent

按 Life OS 的团队约定：只经 life-os MCP 或 PR 写回，流程是 search → read(sha) → update_note；不改 `me/values.md`、规则文件和凭据。写入方式与 Claude.ai 相同（`inbox.md` 队列）。技能源码以本仓库为准，同步到 codex-setup 后各 agent 按需拉取。

## 打包内容

`make package` 打包 `SKILL.md`、`references/`、`templates/`、`schema/`、`scripts/anchor.py` 和 `scripts/anchor_core/`。只用 Python 标准库（3.11+），不需要安装依赖。
