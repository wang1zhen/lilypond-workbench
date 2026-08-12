# LilyPond Workbench

[English](README.md)

LilyPond Workbench 是一个面向 Codex 的 skill，同时也是一套确定性的命令行工具，
用于创建、修改、诊断、分析、导入、排版和发布 LilyPond 乐谱。它把需要音乐判断的
工作交给 agent，把校验、格式转换、分谱生成、和声分析和渲染等应当稳定复现的操作
交给本地工具完成。

项目面向本机安装的 LilyPond 2.24 系列，并以 LilyPond 2.24.4 进行测试。Python
环境及依赖完全由 [uv](https://docs.astral.sh/uv/) 管理。

## 功能

- 根据自然语言创建 `.ly` 乐谱。
- 修改已有 LilyPond 源文件，同时保留变量、include、注释和项目结构。
- 添加歌词、和弦标记、指法、上下两套不同指法、弓法、连音线、乐句连线和延音线。
- 诊断 LilyPond 编译错误和小节时值问题。
- 导入 MusicXML、压缩 MusicXML、MIDI 和 ABC，并整理转换后的 LilyPond 源码。
- 通过版本化清单从共享的总谱源文件生成独立分谱。
- 对相对音高、include、移调、连音组、反复和多声部建立书面音高语义索引，为
  violin、viola 和 cello 推荐稳定的谱号切换，并可选择仅在生成分谱中应用。
- 推断和弦名称、局部调性、转位和罗马数字，并生成供人工复核的 JSON 置信度报告。
- 将单份或多份乐谱渲染为 PDF、PNG、SVG 或 PostScript。
- 通过 `lilypond-book` 构建包含乐谱的 LuaLaTeX 文档。

自然语言创作和音乐判断由 agent 完成；CLI 负责可重复、可验证的机械操作。

## 环境要求

| 依赖 | 说明 |
| --- | --- |
| Python 3.11 或更新版本 | 版本记录在 `.python-version` |
| uv | 唯一支持的 Python 环境和依赖管理工具 |
| LilyPond 2.24.x | 已在 2.24.4 上测试 |
| `musicxml2ly`、`midi2ly`、`abc2ly`、`convert-ly` | 通常随 LilyPond 一同安装 |
| `lilypond-book`、LuaLaTeX、`latexmk` | 仅构建 LaTeX 文档时需要 |

LilyPond 应由操作系统或其他系统级包管理器安装，不属于 Python 依赖。

## 初始化

在仓库根目录运行：

```sh
uv sync --group dev
uv run python scripts/workbench.py doctor
```

`doctor` 会报告 uv、LilyPond、格式转换工具及可选 LaTeX 工具链的版本。缺少可选工具
只会产生警告；使用 `doctor --strict` 可要求全部导入与出版工具均可用。

如需让另一个项目发现本 skill，请把该目录放置或链接到目标项目的
`.agents/skills/lilypond-workbench`。如需跨项目个人使用，则放到
`~/.agents/skills/lilypond-workbench`。

本仓库目录本身就是完整的 skill 包，`SKILL.md` 是 agent 的入口文件。

## 使用 skill

向 Codex 指定 `$lilypond-workbench`，并描述需要的音乐结果，不必把任务拆成一串
LilyPond 命令。例如：

```text
使用 $lilypond-workbench 创作一首两页以内的 E 小调小提琴练习曲，
在五线谱上下添加两套不同指法，检查每小节时值并输出 PDF。
```

```text
使用 $lilypond-workbench 导入这份 MusicXML，清理转换结果，
分析和弦并生成移调后的独立分谱。
```

```text
使用 $lilypond-workbench 分析这份 LilyPond 日志，
只修复导致编译失败和小节时值错误的源代码。
```

skill 会根据任务读取 `references/` 下对应的工作流，并使用 CLI 完成可复现的校验
和产物生成。

## CLI 快速开始

所有 Python 命令都必须通过 uv 运行：

```sh
uv run python scripts/workbench.py --help
```

从模板创建并渲染乐谱：

```sh
uv run python scripts/workbench.py new piano my-score.ly
uv run python scripts/workbench.py validate my-score.ly
uv run python scripts/workbench.py lint my-score.ly --output my-score.lint.json
uv run python scripts/workbench.py render my-score.ly --output-dir build/score
```

导入并清理交换格式文件：

```sh
uv run python scripts/workbench.py import-score input.musicxml \
  --output imported.ly
uv run python scripts/workbench.py clean imported.ly \
  --output imported-clean.ly
```

并发批量渲染：

```sh
uv run python scripts/workbench.py batch-render scores \
  --recursive --jobs 4 --output-dir build/scores
```

生成独立分谱：

```sh
uv run python scripts/workbench.py parts-manifest full-score.ly \
  --output parts.yaml
# 先检查名称、谱号、移调设置和所有 needs_review 项。
uv run python scripts/workbench.py extract-parts parts.yaml --compile
```

在不修改源文件的前提下分析弦乐分谱谱号：

```sh
uv run python scripts/workbench.py analyze-clefs full-score.ly \
  --instrument cello --variable celloMusic \
  --output cello.clefs.json
```

新生成的分谱清单使用 schema v3，并声明 `pitch_basis: concert|written`。保持
`clef.policy: suggest` 只生成带源码定位的报告；改为 `auto` 才会给该分谱添加独立
谱号轨。schema v1 与 v2 仍可读取，并保持原有行为。

分析和声：

```sh
uv run python scripts/workbench.py analyze-harmony progression.ly \
  --key C --output harmony.ily --report harmony.analysis.json
```

构建包含乐谱的文档：

```sh
uv run python scripts/workbench.py build-document article.lytex \
  --output-dir build/document
```

当结果需要交给另一个程序或 agent 步骤处理时，可对支持的命令添加 `--json`。

所有 JSON 命令响应都使用带版本的 envelope，字段固定为 `schema_version`、`ok`、
`command`、`inputs`、`artifacts`、`diagnostics` 和 `metadata`。退出码 0 表示成功，
1 表示检查发现失败项或外部工具失败，2 表示输入/配置无效或缺少必需工具，130 表示
被中断。`lint` 报告在 `metadata.report` 及可选报告文件中使用独立 schema 版本。

## 命令一览

| 命令 | 用途 |
| --- | --- |
| `doctor` | 检查本地工具和版本 |
| `new` | 复制内置乐谱模板 |
| `render` | 编译单个 `.ly` 文件 |
| `batch-render` | 批量、可并发地编译乐谱 |
| `validate` | 检查时值并进行不输出页面的 LilyPond 编译 |
| `lint` | 检查结构、音域、谱号、移调元数据和分谱一致性 |
| `parse-log` | 把 LilyPond 输出解析为结构化诊断 |
| `import-score` | 将 MusicXML、MIDI 或 ABC 转换为 LilyPond |
| `clean` | 统一 LilyPond 版本声明并格式化源码 |
| `parts-manifest` | 发现分谱候选并生成可审阅的清单 |
| `extract-parts` | 根据审阅后的清单生成分谱 wrapper |
| `analyze-harmony` | 生成和弦、罗马数字 include 及分析报告 |
| `analyze-clefs` | 从语义索引推荐 violin、viola 或 cello 的谱号切换 |
| `build-document` | 运行 `lilypond-book` 和 LuaLaTeX |

可通过 `uv run python scripts/workbench.py COMMAND --help` 查看完整参数。

## 内置模板

`new` 支持以下模板名称：

- `single-staff`、`piano`、`lead-sheet`、`satb`
- `string-quartet`、`orchestra`、`parts-project`
- `guitar`、`ukulele`、`bass`、`drum-kit`、`annotations`

通用样式位于 `assets/styles/house-style.ily`，文档模板位于
`assets/documents/article.lytex`。

## 项目结构

```text
.
├── SKILL.md                 # Codex 加载的精简指令
├── agents/openai.yaml       # skill 界面元数据
├── assets/                  # 乐谱和文档模板
├── references/              # 按任务拆分的 agent 工作流
├── scripts/
│   ├── workbench.py         # CLI 入口
│   └── lilypond_workbench/  # 确定性工具实现
├── tests/                   # 单元测试和工具链集成测试
└── evals/evals.json         # 贴近真实请求的 skill 评估任务
```

## 开发约定

依赖修改和 Python 程序运行一律使用 uv：

```sh
uv add PACKAGE
uv remove PACKAGE
uv add --dev PACKAGE
uv run pytest
```

运行 7 个可执行 skill 评测：

```sh
uv run python scripts/run_evals.py
```

处理不可信 LilyPond 输入时，构建隔离 runner，并把输出放在源目录之外：

```sh
docker build -t localhost/lilypond-workbench:2.24.4 -f containers/Dockerfile .
uv run python scripts/workbench.py --runner container render score.ly \
  --output-dir /tmp/lilypond-output
```

不要手动修改 `pyproject.toml` 或 `uv.lock` 中的依赖列表，也不要绕过 `uv run`
直接调用 `python`、`pytest` 或项目脚本。

当系统没有安装 LilyPond 或 LaTeX 工具链时，只运行快速测试：

```sh
uv run pytest -m "not integration"
```

在安装完整工具链的机器上运行全部测试：

```sh
uv run pytest
```

完整测试会编译所有内置乐谱模板，并覆盖格式导入、批量渲染、错误检测、分谱生成、
和声分析和 LaTeX 文档构建。

## 重要行为与限制

- 格式转换结果始终应视为草稿。MusicXML 布局、MIDI 量化与等音拼写、ABC 方言
  细节都需要人工进行音乐性复核。
- 和声分析面向十二平均律下的传统功能和声、流行与爵士语汇。低置信度结果不会
  写入 LilyPond include，但会保留在 JSON 中供复核。
- 当共享总谱无法安全拆分时，分谱工具会主动停止；编译前必须检查 manifest。
- 自动谱号轨不会修改总谱源文件；已有显式谱号会被保留，出版前必须复核分析报告。
- LilyPond 文件可以嵌入 Guile/Scheme，应当把输入视作可执行代码。不可信乐谱
  只能在适当隔离的环境中编译。
- `--force` 和 `--in-place` 会覆盖文件，使用前必须确认目标路径。
