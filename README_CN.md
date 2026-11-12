# LilyPond Workbench

[English](README.md)

面向 Codex 的 skill 与本地 LilyPond 工具集：创作和修改乐谱、导入文件、检查改动、
生成分谱、分析和声，以及渲染和出版。音乐判断交给 agent，可重复的检查与构建交给 CLI。

## 快速开始

需要 **Python 3.11+**、[uv](https://docs.astral.sh/uv/) 和系统安装的 **LilyPond 2.24.x**
（测试版本为 2.24.4）。导入需要 LilyPond 自带的转换工具；出版另需 `lilypond-book`、
LuaLaTeX 和 `latexmk`。

在仓库根目录运行，所有 Python 命令一律通过 uv：

```sh
uv sync --group dev
uv run python scripts/workbench.py doctor
uv run python scripts/workbench.py new piano my-score.ly
uv run python scripts/workbench.py validate my-score.ly
uv run python scripts/workbench.py lint my-score.ly --output my-score.lint.json
uv run python scripts/workbench.py render my-score.ly --output-dir build/score
```

`doctor` 检查工具可用性；`doctor --strict` 要求导入与出版工具全部可用。
各命令的完整参数见 `COMMAND --help`。

## 作为 skill 使用

把本仓库放置或链接到项目的 `.agents/skills/lilypond-workbench`；个人跨项目使用时，
放到 `~/.agents/skills/lilypond-workbench`。仓库本身就是 skill 包，入口为
[SKILL.md](SKILL.md)。

向 Codex 描述音乐目标即可：

> 使用 $lilypond-workbench 创作一首 E 小调小提琴练习曲，添加两套可选指法，
> 检查每小节时值并渲染 PDF。

## 命令一览

运行方式：`uv run python scripts/workbench.py COMMAND`。

| 命令 | 用途 |
| --- | --- |
| `doctor` | 检查工具和版本 |
| `new` | 从模板创建乐谱 |
| `render` | 编译为 PDF、PNG、SVG 或 PostScript |
| `batch-render` | 批量编译，可并行 |
| `validate` | 检查时值并进行不输出页面的编译 |
| `lint` | 检查结构、音域、谱号和分谱一致性 |
| `parse-log` | 将编译日志转为结构化诊断 |
| `import-score` | 导入 MusicXML/MXL、MIDI 或 ABC |
| `clean` | 统一版本声明和格式 |
| `parts-manifest` | 发现声部并生成待复核清单 |
| `extract-parts` | 生成分谱 wrapper，可编译 PDF |
| `analyze-harmony` | 推断和弦、调性和罗马数字，输出置信度报告 |
| `analyze-clefs` | 推荐 violin、viola、cello 谱号切换 |
| `index` | 输出一个音乐变量的语义索引 |
| `diff` | 比较音乐内容并定位变化 |
| `build-document` | 通过 lilypond-book 和 LuaLaTeX 出版 |

### 常用工作流

导入并清理：

```sh
uv run python scripts/workbench.py import-score input.musicxml --output imported.ly
uv run python scripts/workbench.py clean imported.ly --output imported-clean.ly
```

生成分谱；提取前先复核名称、移调及 `needs_review` 项：

```sh
uv run python scripts/workbench.py parts-manifest full-score.ly --output parts.yaml
uv run python scripts/workbench.py extract-parts parts.yaml --compile
```

检查编辑范围：

```sh
uv run python scripts/workbench.py diff before.ly after.ly \
  --variable violinMusic --expect-measures 37-40 --output changes.json
```

`diff` 忽略格式和注释。`--fail-on-change` 要求音乐完全未变；变量改名后使用
`--new-variable`。事件和标记移动时，新旧小节都必须位于允许修改的范围内。

自动化调用可加 `--json`。响应字段为 `schema_version`、`ok`、`command`、`inputs`、
`artifacts`、`diagnostics`、`metadata`。
退出码：**0** 成功；**1** 检查失败或工具失败；**2** 输入/配置无效或缺少工具；
**130** 中断。

## 安全与限制

**LilyPond 源码能执行 Guile/Scheme，不要在宿主机直接编译不可信文件。**
支持的命令可使用隔离 runner，输出必须位于源目录之外：

```sh
docker build -t localhost/lilypond-workbench:2.24.4 -f containers/Dockerfile .
uv run python scripts/workbench.py --runner container render score.ly \
  --output-dir /tmp/lilypond-output
```

- 镜像仅支持 **Linux amd64**。ARM 主机需 amd64 模拟支持，并使用
  `docker build --platform linux/amd64`。覆盖 `LILYPOND_VERSION` 时，必须同时提供
  核实过的 `LILYPOND_SHA256`；下载会在解压前校验。
- 容器模式仅支持 `render`、`batch-render`、`validate`、`lint`、`analyze-harmony`，
  不是所有 CLI 命令的通用沙箱。
- `--force`、`--in-place` 会覆盖文件，使用前确认目标。
- 导入结果是草稿。和声分析面向十二平均律的传统、流行与爵士语汇；低置信度和弦只保留
  在 JSON 中，不写入 include。`--score-index` 只能选择输入文件直接声明的非嵌套 score；
  MIDI 输出不明确时会拒绝分析。
- 分谱编译前需人工复核。清单使用 schema v3，兼容读取 v1/v2；`source` 相对清单目录。
  ID 和 `output_name` 必须是安全文件名，ID 不可重复，`_shared` 为保留名。
  非法音域或移调配置会报配置错误，不能通过 suppression 隐藏。
- 含 include 或 `\cadenzaOn` 的源码会将静态时长分析交给编译器验证；
  静态检查通过本身不能证明乐谱正确。
- `index`、`diff` **每次处理一个变量**，使用书面音高，不重新拼写移调临时记号。
  紧接 `\tempo` 的 `\repeat` 会触发解析器限制警告。支持字面时值的 `\after`
  力度/演奏记号及默认 `\afterGrace`；其他 `\after` 形式、afterGrace 显式比例和
  `afterGraceFraction` 覆盖会被拒绝。
- 谱号建议不会修改源文件，已有显式谱号保持优先。

## 指南与模板

任务指南：[语义比较](references/comparison.md)、[诊断](references/diagnostics.md)、
[导入](references/imports.md)、[分谱](references/parts.md)、
[谱号与音域](references/instruments.md)、[和声](references/harmony.md)、
[演奏标记](references/annotations.md)、[排版](references/engraving.md)、
[lint](references/linting.md)、[LaTeX](references/latex.md)。

`new` 模板：`single-staff`、`piano`、`lead-sheet`、`satb`、`string-quartet`、
`orchestra`、`parts-project`、`guitar`、`ukulele`、`bass`、`drum-kit`、`annotations`。
通用样式在 `assets/styles/house-style.ily`，文档模板在 `assets/documents/article.lytex`。

## 开发

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。依赖变更使用 `uv add`、`uv remove`、
`uv add --dev`，不要手动编辑依赖列表或 `uv.lock`。

```sh
uv run pytest -m "not integration"          # 快速测试，无需系统工具链
uv run pytest                               # 全量测试，需要 LilyPond 和 LaTeX
uv run python scripts/validate_skill.py .
uv run python scripts/run_evals.py           # 全部 8 个回归场景
uv run python scripts/run_evals.py --id 8    # 时长与诊断回归
```

Eval 运行映射的 pytest 测试，**不会执行 agent prompt**，不能据此证明所有任务目标、
页数、可演奏性或 agent 编辑质量。

目录速览：`scripts/lilypond_workbench/` 为 CLI 实现，`tests/` 为测试与用例，
`evals/evals.json` 为回归场景映射，`references/` 为按任务拆分的指南。
