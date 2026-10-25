# 命令流程

每个流程都给出终端命令（Claude Code）和 MCP 写法（Claude.ai 等，见 [runtimes.md](runtimes.md)）。回复用中文、短句；不解释原理，除非本人问。

## now

触发时刻。本人发来一句话，例如「她说想自己待会」「我在想她是不是跟别人在玩」。

1. **只问两个数**，一条消息：「两个数：这个想法你多确定（0–100%）？想去确认的冲动（0–10）？」本人已经给了就跳过。
2. 拿到数后，回复 **不超过 5 行**：
   - 记下的编号和两个数；
   - 抛锚（60–90 秒）：承认「我注意到我有一个想法：……」→ 回到身体：双脚踩地、呼气比吸气长、找到最紧的地方让它在 → 投入当下：看清眼前三样东西；
   - 需要回对方时给最短脚本：想休息/自己待 →「好，你先休息。」；场面冷下来 →「那先聊到这里。」；提分手 →「好，那就这样。」说完停，不解释；
   - 「现在去做：X」，X 从 `actions.md`（事业/健康/社交）里取；
   - 「24–72 小时后我问你事实。」
3. 写 episode：trigger 写对方可观察的言行（原话最好），my_thought 写本人原话，不改写。
4. 不做的事：不分析对方为什么这样，不说"她应该没事"，不讨论要不要继续这段关系，不追问细节。

```bash
python3 scripts/anchor.py now --trigger "她说想自己待会" --thought "她是不是不要我了" \
  --body "胸口发紧" --certainty 70 --urge 8 --conditions 半夜,电话
# 之后本人说了做了什么：
python3 scripts/anchor.py act ep-2026-10-26-01 --action said_ok --miss no
```

终端输出就是给本人的 5 行，直接转述即可。`--json` 给机器读。

动作取值：`checked` 去确认/查看；`chased` 追着找、挽留、解释、不肯挂电话；`held` 有冲动但没去确认；`said_ok` 说了「好」；`said_stop` 说了「先聊到这里/那就这样」；`said_no` 说了不；`other`。`miss`：想做到的没做到为 true。

## fact

24–72 小时后（`anchor.py status`/`due` 会列出来）问一句：「ep-… 那次你想的是『……』。后来可观察到的事实是什么？」

- 只接受可观察的事：几点回来、做了什么、有没有发生。
- 本人说"她说不是""她解释了"→ `unverifiable`。脚本会自动把带解释口吻的事实改记为 unverifiable，若那句话本身就是被预测的事件（例如预测"她会提分手"，事实是"她在电话里提了分手"），加 `--observed`。
- 无法核实是最多的一类，这是正常的：在"不知道"里待着、不去确认，就是训练本身。
- 顺手问恢复用了多久（分钟）、最难受时 SUDS（0–100），有就记。

```bash
python3 scripts/anchor.py fact ep-2026-10-26-01 --outcome not_happened \
  --fact "第二天中午她约我吃饭" --recovery-minutes 40 --suds-peak 75
```

## drill

每日 10 分钟。`/drill hot`：先 60 秒爬楼或单车冲刺，喘着开始。

```bash
python3 scripts/anchor.py drill          # 或 drill --hot
```

脚本自动选剧本（按 2/4/7/14/30 天间隔重复，同一剧本不连续两天练；最近 14 天 miss 条件相同的剧本加权；没练过的剧本略优先，保证场景多样；连续两次开练 SUDS < 40 的剧本往后放，换更贴近的）并附一条到期见地。流程：

1. 30 秒接地；开练 SUDS。
2. 出声慢读剧本。
3. 3 轮：bot 说出对方那句话（cue），本人 **3 秒内出声** 说脚本，说完就停；带着不舒服停留 30 秒。轮次按文字/电话/当面轮换，优先本人 miss 过的渠道。
4. 读一条见地，第二遍出声。
5. 收尾 SUDS；三个是/否：3 秒内？照字？停住了？
6. 记录：

```bash
python3 scripts/anchor.py drill log --scene sc-2026-08-28-01 --view V03 \
  --suds-before 60 --suds-after 35 --within-3s yes --verbatim yes --held yes
```

bot 陪练时只评这三项，不点评内容。语音：`drill --narration /tmp/drill.txt` 导出纯文本（带停顿标记），可交给 TTS（macOS `say -f /tmp/drill.txt`，或个人 IP 工作室的配声流程）。

`drill plan --days 7 --start YYYY-MM-DD --hot-days 3,6` 预先生成一周演练稿到 `drills/`。

## ladder

主体性靠阶梯，不靠演练。先关系外（点餐、同事、朋友），后关系内（说偏好 → 提一个要求 → 说不）。

```bash
python3 scripts/anchor.py ladder                      # 下一级是什么
python3 scripts/anchor.py ladder done L01 --suds 30   # 做完记日期与 SUDS
```

同一级完成两次、且最近一次 SUDS ≤ 40 就升级；本人也可以手动打勾。bot 只给下一级任务和一句「做完告诉我日期和 SUDS」，不替本人挑关系里的具体事。

## view

```bash
python3 scripts/anchor.py view               # 今天到期的一条
python3 scripts/anchor.py view done V03      # 读完；没进去用 --again，明天再来
```

推送格式：见地一句 + 出处（本人原话优先）+「读两遍，第二遍出声」。不加解释。

## review

历史素材是从旧对话里抽出来的（`origin: export`，`review: pending`），本人核对后才算定稿。

```bash
python3 scripts/anchor.py review                                  # 待核对/已确认/已否掉，列出下 10 条
python3 scripts/anchor.py review ep-2026-08-25-03 --confirm
python3 scripts/anchor.py review ep-2026-01-15-02 --reject --note "不是我写的"
python3 scripts/anchor.py review --sheet areas/relationship/extraction/2026-10-25-sample.md
```

抽样核对表里每条末尾是「核对：□ 对　□ 错：」，把「□ 对」改成「☑ 对」表示确认，在「错：」后写原因表示否掉，然后用 `--sheet` 一次导入。抽样全部核对通过后，`anchor.py review --accept-pending` 把其余待核对记录标为 `accepted`（批次验收，不等于逐条确认），之后仍可单独否掉。否掉的 episode 留在文件里（不删原始记录），但它的剧本不再进入演练选题，也不计入周报。bot 只记录本人的判断，不替本人确认。

## weekly

```bash
python3 scripts/anchor.py weekly --write              # 本周
python3 scripts/anchor.py weekly --week 2026-44 --write
```

周报包含：未确认率、执行率、冲动趋势（近 4 周）、校准（当时确定 % vs 实际发生率、Brier）、恢复时间、无法核实数、待回填、演练次数与 SUDS、阶梯进度、每条 miss 的复盘模板（发生了什么 / 我想了什么 / 身体 / 我做了什么 / 下次 if-then）和一段给咨询师的话。

给本人看时：先说 3 个数（未确认率、执行率、校准），再贴给咨询师的话，请本人填「想和你讨论的一件事」和每条 miss 的 if-then。不评价本人"进步/退步"，只报数。

指标定义：
- 未确认率 = 有行动记录的触发里，行动不是 `checked`/`chased` 的比例。
- 执行率 = `miss` 已判定的触发里，`miss=false` 的比例。
- 校准只用 `happened`/`not_happened` 的事件；`unverifiable` 单独计数。
