# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

中文 | [English](./README.md)

一个面向 Codex 本地 skill 库的自动选择与路由器。

它会扫描安装者自己的 skill，建立本地多级索引，根据当前请求自动走完分类路径，并只把最终几个最合适的 skill 交给用户选择。用户不需要理解或逐层选择领域、专科、任务类型、技术栈等内部分类。

## 核心能力

- 自动发现一个或多个本地 skills 根目录。
- 全文分类每个 `SKILL.md`，生成多标签本地索引。
- 自动完成领域、专科、任务、技术、输出和环境要求路由。
- 通过本地 SQLite 索引只查询当前选中的分类路径。
- 默认只返回最终加权候选，不展示中间分类。
- 仅在用户选定 skill 后读取其完整说明。
- 同一工作流中持续使用已选 skill，避免每轮重复选择。
- 在下载依赖、配置账号或使用 API Key 前要求确认。
- 增量刷新新增或修改的 skill，不必每次重建全部索引。
- 合并完全重复内容，同时保留同名但内容不同的有效版本。
- 通过本地选择记忆和自增长报告持续改善匹配效果。

## 工作方式

```text
用户请求
   |
   v
打开预先构建的本地索引
   |
   v
自动多级路由（内部完成）
   |
   v
最终 1-4 个候选 skill
   |
   v
用户选择并激活 skill
```

内部索引可以包含以下分面：

```text
一级领域 -> 二级领域 -> 专科 -> 任务类型 -> 技术栈 -> 输出类型 -> 环境要求
```

这些分面只用于程序内部缩小候选范围。正常使用不会要求用户逐层分类。只有维护分类规则时，才需要显式使用 `--show-branches` 查看分支。

默认路由使用本地 SQLite 数据库。前台阶段只查询分类名称和数量；每自动选择一级分类，只会把临时候选表缩小一次；到达最终叶子后，才读取该分类中的候选卡片。未选中的分类不会被解析成 Python 对象，也不会进入模型提示词。

## 快速安装

要求 Python 3.10 或更高版本。PowerShell 仅用于 Windows 兼容工具，不是核心运行依赖。

```bash
git clone https://github.com/lhz1315937650/skill-selection-assistant.git
cd skill-selection-assistant
python scripts/install-skill.py
```

安装器会：

1. 将 skill 安装到 `$CODEX_HOME/skills/skill-selection-assistant`。
2. 扫描安装者自己的 skills 根目录。
3. 构建 `.skill-index/deep/` 本地索引。
4. 执行一次推荐健康检查。
5. 保留本机索引、选择记忆和其他非托管文件。

安装前预览，不写入文件：

```bash
python scripts/install-skill.py --dry-run
```

更新已有安装：

```bash
python scripts/install-skill.py --force
```

检查当前安装：

```bash
python scripts/install-skill.py --check
```

使用自定义 Codex Home：

```bash
python scripts/install-skill.py --codex-home "<codex-home>"
```

扫描多个 skills 根目录时可重复传入：

```bash
python scripts/install-skill.py --skills-root "<root-a>" --skills-root "<root-b>"
```

## 启用自动选择

安装 skill 文件并不代表允许修改全局指令。需要在普通请求前自动运行选择器时，明确执行：

```bash
python scripts/install-skill.py --configure-agents
```

该参数只维护带边界标记的 `AGENTS.md` 区块，不会覆盖其他用户指令。生成的规则会要求 Codex：

- 先运行本地推荐器。
- 不向用户显示中间分类。
- 只展示最终加权候选 skill。
- 用户选定后在当前工作流中持续使用。

## 使用

推荐使用跨平台 Python 入口：

```bash
python scripts/recommend-skills.py --query "帮我优化这个 React 项目的交互体验" --compact
```

默认结果会直接到达最终候选：

```json
{
  "schema_version": "3.0.0",
  "mode": "choose_skill",
  "branches": [],
  "candidates": [
    {
      "name": "example-skill",
      "function_summary": "...",
      "score": 108
    }
  ]
}
```

`route_trace` 会保留自动选择的内部路径，供诊断使用，但不应作为用户选择界面。

分类维护时显式查看第一层分支：

```bash
python scripts/recommend-skills.py --query "帮我优化这个 React 项目" --show-branches
```

Windows PowerShell 兼容入口具有相同的默认行为：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/recommend-skills.ps1 -Query "帮我优化这个 React 项目"
```

## 本地索引

索引保存在已安装 skill 的 `.skill-index/` 中，只属于当前用户。主要内容包括：

- `deep/metadata.json`：索引版本、来源目录和分类状态。
- `deep/source-manifest.json`：文件路径、大小、修改时间和分类状态。
- `deep/skills-deep-index.ndjson`：逐项技能分类记录。
- `deep/facets.json`：多标签倒排分面。
- `deep/route-cards.json`：轻量路由卡片。
- `deep/lazy-route.sqlite3`：普通请求使用的懒加载路由数据库。
- `DETAILED_CLASSIFICATION.md`：人类可读的技能分类地图。
- `domain-task-matrix.csv`：领域与任务类型交叉表。
- `selection-memory.md`：本地选择反馈。

`.skill-index/` 不会进入发布包，也不应提交到 Git。仓库发布的是扫描、分类和路由能力，不包含作者电脑上的 skill 清单、绝对路径或私有索引。

`facets.json` 和 `route-cards.json` 会继续作为可移植的来源与审计文件。首次使用时，`lazy-index.py` 会直接把它们转换为 SQLite，不会重新读取原始 skill 正文。后续请求只打开数据库并查询当前路径。仅在兼容性测试时使用 `deep-route.py --json-router` 回退到旧的整份 JSON 路由。

## 索引生命周期与恢复

全量分类只发生在安装、更新或显式维护时。普通推荐只校验必需的索引文件，打开 SQLite，然后查询当前命中的分类路径；即使旧的新鲜度缓存已经过期，也不会递归枚举 skills 根目录中的全部 `SKILL.md`。

确实需要在当前请求中核对全部来源时，显式使用 `--strict-freshness`。`--force-freshness-check` 同样会进入严格模式，并忽略以前的严格检查缓存。PowerShell 对应参数为 `-StrictFreshness`。

手动诊断：

```bash
python scripts/doctor.py
```

自动修复：

```bash
python scripts/doctor.py --fix
```

完全重建分类：

```bash
python scripts/recommend-skills.py --query "health check" --strict-freshness
python scripts/recommend-skills.py --query "health check" --full-rebuild
```

分类失败会记录在来源清单中。默认索引可在降级状态下继续使用已成功分类的 skill；CI 或审计可以在分类器上使用 `--strict`。

## 选择记忆与自增长

记录一次选择：

```bash
python scripts/record-selection-memory.py \
  --query "帮我做一个前端页面" \
  --outcome selected \
  --selected-skill "frontend-design" \
  --route-type specialty \
  --category frontend-style-ui
```

默认不保存原始请求。只有显式添加 `--store-query` 时才会保存缩短后的请求文本。

生成本机技能库自增长报告：

```bash
python scripts/self-grow.py
```

报告会分析过大的分类、重复候选、常见任务、失败匹配和可能缺失的 skill，但不会自动修改用户的 skill 文件。

## 安全边界

- 不自动下载依赖、模型或工具链。
- 不自动假设账号、API Key、浏览器配置、工作区或发布目标。
- 不修改被索引的 skill。
- 不发布或提交本地索引。
- 不把作者机器上的路径和技能数量作为其他用户的默认值。
- 安装更新只替换受管文件，并在失败时回滚；`.skill-index/` 会被保留。

## 开发与测试

跨平台 Python 回归测试：

```bash
python tests/run-python-smoke-tests.py
```

Windows PowerShell 回归测试：

```powershell
powershell -ExecutionPolicy Bypass -File tests/run-smoke-tests.ps1
```

测试覆盖自动最终候选路由、显式分类调试、增量索引、重复项处理、多根目录、隐私优先的选择记忆、安装回滚、空技能库和索引修复。

构建发布包：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/package-release.ps1 -Version v1.8.1
```

## 项目结构

```text
skill-selection-assistant/
|-- scripts/                         # 安装、清理与发布
|-- tests/                           # Python 与 PowerShell 回归测试
|-- skill-selection-assistant/
|   |-- SKILL.md                     # Codex skill 指令
|   |-- VERSION
|   |-- agents/openai.yaml
|   |-- rules/categories.json
|   |-- schemas/recommendation-v3.schema.json
|   |-- references/                  # 按需加载的维护文档
|   `-- scripts/                     # 分类、路由、诊断与记忆工具
|-- INSTALLATION_BEHAVIOR.md
|-- SELF_GROWTH.md
`-- CHANGELOG.md
```

更多维护细节：

- [安装与本地边界](./INSTALLATION_BEHAVIOR.md)
- [自增长设计](./SELF_GROWTH.md)
- [版本变更](./CHANGELOG.md)

## License

[MIT](./LICENSE)
