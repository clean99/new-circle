# new-circle · anchor-training

抛锚与主体性训练的 skill：把触发时刻、演练、见地和"说不"的阶梯做成每天能照着做的流程，并用预测→事实日志看自己的行为和校准。可装到 Claude Code、Claude.ai 和其他接入 Life OS 的 agent。

- **代码在这里，数据不在这里。** 这是公开仓库，只放通用代码、模板和测试；所有个人记录都写在私有的 Life OS 知识仓库 `areas/relationship/` 下。
- 只用 Python 标准库（3.11+）。

## 命令

| 命令 | 用途 |
|---|---|
| `/now` | 触发时刻：两个数（确定 %、冲动 0–10）→ 抛锚 → 最短脚本 → 现在去做 X → 记录，24–72 小时后追问事实 |
| `/fact` | 回填可观察事实；对方的解释记为无法核实 |
| `/drill`、`/drill hot` | 每日 10 分钟演练：接地 → 读剧本 → 3 秒内出声说脚本 → 带着不舒服停 30 秒 → 见地 → SUDS |
| `/ladder` | 主体性阶梯的下一级与完成记录 |
| `/view` | 推一条到期见地（1/3/7/14/30 天） |
| `/weekly` | 未确认率、执行率、冲动趋势、校准、恢复、演练、阶梯、miss 复盘、给咨询师的话 |

终端里对应 `python3 scripts/anchor.py <命令>`，`--help` 看全部参数。流程细节见 [references/protocols.md](references/protocols.md)，数据格式见 [references/data-contract.md](references/data-contract.md)。

## 安装

Claude Code：

```bash
git clone https://github.com/clean99/new-circle.git ~/new-circle
ln -sfn ~/new-circle ~/.codex/skills/anchor-training
ln -sfn ~/.codex/skills/anchor-training ~/.claude/skills/anchor-training
python3 ~/new-circle/scripts/anchor.py init      # 在 Life OS 里建 areas/relationship（不覆盖已有文件）
```

Claude.ai：`make package`，把 `dist/anchor-training.zip` 在 Settings → Capabilities → Skills 上传；需要已连上 life-os MCP。写入经 `inbox.md` 队列，本地 `anchor.py ingest` 合并。见 [references/runtimes.md](references/runtimes.md)。

## 开发

```bash
make lint   # ruff + 技能自检（链接、模板、schema 与代码一致）
make test   # unittest
```

历史素材的导入与抽取流程见 [references/extraction.md](references/extraction.md)。
