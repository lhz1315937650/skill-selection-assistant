# Skill Selection Assistant 中文介绍

Skill Selection Assistant 是一个面向 Codex / Claude Code 类本地技能系统的“技能选择路由器”。它的目标不是替用户预置一套固定技能库，而是在安装后扫描使用者自己电脑里的 skills，根据真实任务先判断领域分类，再只读取对应分类下的候选技能，最后按候选权重用用户当前对话的语言给出简洁推荐。

这样做的核心价值是：减少 token 浪费、避免一次性读取全部技能、降低误触发下载或环境安装的风险，并让大型 skill 仓库可以逐步自我整理、自我校准。

## 它解决什么问题

当本地 skills 越来越多时，常见问题会变成：

- 每次对话都扫描或阅读全部 `SKILL.md`，上下文成本很高。
- 技能名称相似、领域重叠，容易推荐错技能。
- 有些技能会触发依赖安装、模型下载、账号配置或外部工具链，直接执行会有风险。
- 发布给别人使用时，开发者并不知道对方电脑里有哪些 skills，不能硬编码本机分类。

本项目的设计原则是“先路由，再读取”。它先用轻量规则判断任务属于哪个候选池，再读取该候选池的 shortlist，而不是把所有技能一次性塞进上下文。

路由层级不是固定三层。它会根据安装者本机真实 skill 分布自适应选择最小可靠路线：如果一级领域已经足够小，就停在一级；如果二级领域仍然很大，就继续进入具体 specialty；如果 specialty 仍然很大，并且用户请求能识别出任务类型，就继续进入 `specialty + task_type` 的自适应叶子路线。

## 医院式深层路由

对于超大型本机技能库，可以显式运行一次深层索引。它会完整读取每一个已安装的 `SKILL.md`，为每项技能标注多个领域、专科、任务、输出和技术栈标签，并建立自适应的“分诊前台”：

```text
总前台 → 一级领域 → 二级领域 → 专科 → 任务类型 → 技术栈 → 输出类型 → 环境要求 → skill
```

每个 skill 可以同时拥有多个一级领域、二级领域、专科、任务、输出和技术栈标签。默认路由使用本地倒排分面索引：用户每选择一个分类，就与前面条件取交集，因此同一个 skill 可以通过任意合适标签被找到，而不是被限制在唯一主路径。命中但不能继续缩小集合的标签会被识别后自动跳过；用户没有明确下一层技术栈、输出或环境时，系统直接在当前集合中本地排序，不强迫用户选择无关分类。

在安装后的技能选择助手目录中运行：

```powershell
python scripts/deep-classify-skills.py --leaf-target 24
python scripts/deep-route.py --query "用 Anime.js 制作前端动画"
```

生成的 `.skill-index/deep/` 只属于安装者自己的电脑，其中包含详细功能画像、多标签 `facets.json`、轻量 `route-cards.json`、完整证据和人工审计目录，不会提交到仓库或打包发布。普通选择只动态返回当前少量分类；最终候选默认只带 220 字摘要、命中标签和标签总数。只有明确要求详细对比时才使用 `--verbose`。

## 核心工作流

1. 安装本 skill 后，先扫描使用者本机的 skills 根目录。
2. 根据 `SKILL.md` 的名称、描述、路径、关键词和触发规则生成多级分类。
3. 对用户当前对话做意图识别，确定最小可靠路线，而不是固定停在某一层。
4. 只读取该路线下的候选技能 shortlist。
5. 用用户当前对话语言推荐权重最高的一组相关技能，并简短说明用途。
6. 如果候选技能可能需要安装运行时、依赖、模型、工具链或账号配置，先提醒用户并等待确认。
7. 用户选择后，将该 skill 作为当前会话的 active skill。
8. 后续对话如果仍属于同一工作流，则继续沿用该 skill，避免重复选择。

## 发布版与本地版的边界

这个仓库发布的是通用版“技能选择助手”，不是作者本机的 skills 镜像。

- 仓库中不包含作者本机的 `.skill-index/` 扫描结果。
- 仓库中不包含作者本机的技能分类数据、技能数量或绝对路径。
- 安装者电脑里的 skills 可能完全不同，所以所有分类都应在安装后本地生成。
- `.skill-index/` 是运行时产物，只应该存在于使用者本机，不应该打包进发布 zip。
- 规则文件可以提供通用分类逻辑，但不能假设某个用户一定安装了某个具体 skill。

这也是项目最重要的可移植性要求：发布包只提供“如何扫描、分类、路由和推荐”的能力，不携带某一台电脑上的私有索引。

## 推荐安装方式

环境要求：

- Python 3.10 或更高版本；Linux/macOS 可能需要使用 `python3`，Windows 也可以使用 `py -3`
- PowerShell 是可选项；缺少 PowerShell 时，Python 深层索引和推荐仍可正常工作，只跳过旧版兼容报告

克隆或下载仓库并进入仓库根目录后，运行：

```bash
python scripts/install-skill.py
```

安装前可以先查看将要使用的目录和预计技能数量，不写入任何文件：

```bash
python scripts/install-skill.py --dry-run
```

Windows 用户也可以继续使用 PowerShell 安装脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-skill.ps1
```

使用隔离或便携 Codex Home 时，PowerShell 安装器也会默认只扫描该目录自己的 `skills`：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/install-skill.ps1 -CodexHome "<codex home>"
```

它会安装路由器、构建本机深层索引并执行第一次推荐自检。默认输出面向用户的简短摘要；自动化程序可以添加 `--json`。已有安装时，Python 安装器使用 `--force` 更新，同时保留本地运行时索引。

更新会先暂存受管文件，并在发布失败时自动回滚。它只替换 `SKILL.md`、`VERSION`、`agents/`、`references/`、`rules/`、`schemas/` 和 `scripts/`，不会删除 `.skill-index/` 或其他本地文件。

首次扫描后，安装器会尽量生成 `.skill-index/DETAILED_CLASSIFICATION.md`、`.skill-index/detailed-classification.json` 和 `.skill-index/domain-task-matrix.csv`，方便用户直接查看本机 skill 的详细分类分布。

每次推荐前，路由器都会根据 manifest 做一次轻量的新鲜度检查：只比较本机 `SKILL.md` 的路径、大小和修改时间，不会重新读取全部正文。如果安装者新增、删除或修改了 skill，路由器会先重建本机分类索引，再给出推荐，确保候选始终来自这台电脑当前实际安装的 skills。

安装器默认先扫描安装者自己的 skill 目录，再全文构建医院式深层索引。更新时使用 `--force`；使用其他工作流构建深层索引时可以传入 `--skip-deep-index`：

```bash
python scripts/install-skill.py --force
python scripts/install-skill.py --skip-scan
python scripts/install-skill.py --skip-deep-index
python scripts/install-skill.py --check
```

仅安装 skill 文件夹不会自动获得修改全局指令的权限。如需让它在普通请求前自动执行 skill 选择，请明确使用：

```bash
python scripts/install-skill.py --configure-agents
```

该参数只会追加一个有边界标记的托管区块，并保留 `AGENTS.md` 中其他指令。不传此参数时，安装器只显示启用提示，不会修改全局配置。普通文字中提到仓库名不会被误判为已启用；缺失、重复或顺序错误的托管标记会在写入安装文件前安全报错。

安装后的跨平台自检命令：

```bash
python scripts/install-skill.py --check
```

进入已安装的 skill 目录后，也可以直接运行 `python scripts/doctor.py`，不需要保留下载的仓库。使用 `--fix` 可以修复缺失、不完整、损坏、过期或旧协议的深层索引；非标准多根目录可以重复传入 `--skills-root`。

```bash
python scripts/doctor.py --fix
```

PowerShell 用户还可以运行扩展兼容诊断：

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/doctor.ps1 -Fix
```

`-Fix` 会在索引缺失时自动补跑扫描，适合第一次安装后排查问题。

也可以手动安装。

把仓库中的 `skill-selection-assistant/` 文件夹复制到你的 Codex skills 目录中，例如：

```powershell
C:\Users\<YourUser>\.codex\skills\skill-selection-assistant
```

如果你使用了自定义 `CODEX_HOME`，请放到：

```powershell
$env:CODEX_HOME\skills\skill-selection-assistant
```

安装后，建议先运行一次本地扫描。

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/scan-local-skills.ps1
```

## 推荐技能示例

推荐使用跨平台 Python 入口测试技能推荐；它不依赖 PowerShell，并返回统一的 `3.0.0` 输出协议：

```bash
python skill-selection-assistant/scripts/recommend-skills.py --query "帮我做一个前端页面"
```

Windows / PowerShell 也可以使用等价入口：

```powershell
powershell -ExecutionPolicy Bypass -File skill-selection-assistant/scripts/recommend-skills.ps1 -Query "帮我做一个前端页面"
```

深层索引首次构建会全文读取安装者当前配置目录下的每个 `SKILL.md`。后续刷新默认只重新分类新增或修改的文件，并复用未变化的分类；只有显式传入 `--full-rebuild` 才执行全量重建。来源清单会保留分类失败的文件，避免索引刚生成就被误判为过期。安装器和分类器都支持重复传入多个 skills 根目录。

推荐结果应当遵循三个原则：

- 先确定任务分类，再读取对应分类候选，不读取全量技能。
- 分类层级自适应：能用 `specialty` 或 `adaptive-leaf` 缩小候选池时，就不退回更大的领域池。
- 根据候选权重动态推荐，不再硬性限制为 1-3 个；强匹配可以少推荐，分数接近时可以多推荐。
- 默认动态推荐会用 `MinRelevanceScore` 过滤偏题候选，避免大库里“分数高但和当前任务关系弱”的 skill 混进来。
- 推荐说明使用用户当前对话的语言。

## 本地生成的索引文件

扫描后会在 skill 目录下生成 `.skill-index/`。常见文件包括：

- `manifest.json`：当前本地索引的摘要和版本信息。
- `route-summary.json`：轻量分类路由摘要。
- `shortlists/`：每个分类下的候选技能列表。
- `shortlists/adaptive-leaf/`：根据本机真实 skill 分布生成的自适应叶子路线，例如 `specialty=document-pdf-ocr|task=extract`。
- `parsed-skills-cache.ndjson`：解析缓存，用于减少重复读取成本。
- `selection-memory.md`：选择反馈与自增长记忆。
- `DETAILED_CLASSIFICATION.md`：人类可读的本机 skill 详细分类地图。
- `domain-task-matrix.csv`：二级领域和任务类型的交叉表，适合后续分析和调参。

默认情况下，本项目不会生成完整大路由文件。只有在明确需要调试或审计时，才建议使用 `-IncludeFullRoutes`。

## 自增长逻辑

Skill Selection Assistant 的自增长不是自动替用户乱改技能，而是把每次选择过程中的经验沉淀下来：

- 哪些任务经常被归到同一类。
- 哪些技能经常被推荐但用户没有选择。
- 哪些技能名称相似、职责重叠，需要更细分。
- 哪些任务没有合适技能，应该提示用户新增或整理 skill。
- 哪些分类 shortlist 太大，需要进一步拆分以节省 token。
- 哪些自适应叶子路线仍然太大，需要继续增加新的分诊轴。

随着使用次数增加，它会更清楚“先看哪个分类、读取哪些候选、什么时候需要提醒用户确认环境安装”。

当用户选择了某个 skill，或者发现推荐不准时，可以把这次反馈记录到本地记忆：

```bash
python skill-selection-assistant/scripts/record-selection-memory.py --query "帮我做一个前端页面" --outcome selected --selected-skill "frontend-design" --route-type domain_detail --category frontend-web
```

默认不会保存用户原始请求；只有显式添加 `--store-query` 才保留缩短后的请求文本。这份本地记忆会参与后续兼容路线内的排序，从而减少重复错配和无效 token 消耗。

## 开发与发布检查

运行烟雾测试：

```powershell
powershell -ExecutionPolicy Bypass -File tests/run-smoke-tests.ps1
```

清理本地运行产物：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/clean-local-artifacts.ps1
```

构建发布包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package-release.ps1 -Version vX.Y.Z
```

发布包必须排除：

- `.skill-index/`
- `dist/`
- 任何只属于开发者本机的扫描结果、缓存、绝对路径或私有分类。

## 适合谁使用

这个项目适合已经积累了较多本地 skills 的用户，尤其是：

- 想让 Codex 在对话开始时自动判断该用哪个 skill。
- 想减少读取全部 skills 带来的 token 浪费。
- 想把技能库整理成多级分类，但不想手动维护全部索引。
- 想发布一个适合多数人安装的通用 skill 选择器，而不是只适配自己电脑的硬编码版本。

一句话总结：它是一个让本地 skills 从“越多越乱”变成“越用越准”的轻量路由层。
