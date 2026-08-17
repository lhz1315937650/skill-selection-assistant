# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![Smoke Tests](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

中文说明 | [English](./README.md)

一个面向大型 Codex 本地 skill 库的自动懒加载路由器。

Skill Selection Assistant 在构建索引时完成 skill 分类，并把分类结果保存在本地。普通请求只查询当前相关的 SQLite 分类路径，不会递归重新读取全部 `SKILL.md`，不会要求用户逐层选择分类，只返回最终几个加权候选 skill。

## 为什么需要它

几十个 skill 可以直接遍历；当本地库增长到几千甚至上万个 skill 时，每个请求都检查完整目录会带来明显的等待时间和 token 浪费，同时大量完全无关的 skill 也可能进入上下文。

本项目采用类似前端懒加载的方式：

1. 仅在安装、更新或显式维护时分类完整 skill 库。
2. 把紧凑分面和候选卡片写入本地私有索引。
3. 根据当前请求自动判断分类路径。
4. 只在 SQLite 中查询命中的分类。
5. 返回最终合适的 skill，选定后才读取完整 `SKILL.md`。

## 核心能力

- 面向大型本地 skill 库的 SQLite 懒加载路由。
- 分类命中较弱时自动使用 SQLite FTS5/BM25 召回并重排。
- 自动完成领域、专科、任务、技术栈、输出类型和环境要求分类。
- 普通推荐不执行递归源文件新鲜度扫描。
- 不向用户展示逐层分类选择过程。
- 使用紧凑 JSON 输出，降低提示词和日志 token 占用。
- 支持用户目录、系统目录及自定义多 skills 根目录。
- 显式刷新时只重新分类新增或修改的 skill。
- 合并完全重复内容，同时保留有意义的同名版本。
- 默认不保存原始请求内容的本地选择记忆。
- Python 3.10+ 核心，并提供可选 PowerShell 兼容入口。

## 工作架构

```text
安装 / 更新 / 显式维护
    -> 发现所有 SKILL.md
    -> 分类并构建本地索引
    -> 发布 lazy-route.sqlite3

普通请求
    -> 打开现有 SQLite 索引
    -> 内部自动选择分类
    -> 持续缩小候选集合
    -> 只读取最终路径的候选卡片
    -> 如果置信度不足：全局召回 Top N 卡片并重排
    -> 返回最终加权 skill
```

默认请求路径不会遍历全部源 skill 文件。只有创建、修复索引或用户明确要求严格检查时，才会核对完整来源目录。

### 召回与重排兜底

分类路由仍然是最快的主路径。当分类没有候选、最高得分过低，或候选太少且没有强命中时，系统自动启用兜底。它只在 SQLite 紧凑字段中执行 FTS5/BM25 检索，默认最多召回 30 张卡片，再结合名称、能力标签、描述、来源、重复信息和本地选择记忆进行重排。

兜底完全在本地确定性运行，不会重新打开源 `SKILL.md`，不会调用 Embedding API，不会下载模型，也不会递归扫描整个文件系统。

## 性能验证

在包含 11,595 个 skill 的 Windows 环境中实测：

| 调用入口 | 删除新鲜度缓存后的耗时 | 存储模式 | 全库源文件扫描 |
|---|---:|---|---|
| Python | 2.408 秒 | `sqlite_lazy` | 否 |
| PowerShell | 3.345 秒 | `sqlite_lazy` | 否 |

两次测试前都删除了新鲜度缓存，普通推荐完成后缓存没有被重新生成，证明请求没有递归枚举源 skill 库。

## 安装

要求 Python 3.10 或更高版本。PowerShell 为可选兼容工具。

```bash
git clone https://github.com/lhz1315937650/skill-selection-assistant.git
cd skill-selection-assistant
python scripts/install-skill.py
```

安装器会复制托管文件、发现配置的 skills 根目录、构建本地私有索引，并运行健康检查。

通过受控的 `AGENTS.md` 区块启用 Codex 自动选择：

```bash
python scripts/install-skill.py --configure-agents
```

常用安装命令：

```bash
# 只预览安装计划
python scripts/install-skill.py --dry-run

# 更新托管文件并保留本地索引
python scripts/install-skill.py --force

# 检查已有安装
python scripts/install-skill.py --check

# 索引多个 skill 根目录
python scripts/install-skill.py --skills-root "<root-a>" --skills-root "<root-b>"
```

## 使用

```bash
python scripts/recommend-skills.py \
  --query "生成一个现代 React 后台管理界面" \
  --compact
```

普通请求会直接到达最终候选：

```json
{
  "mode": "choose_skill",
  "storage_model": "sqlite_lazy",
  "selection_model": "multi_label_facet_intersection",
  "index": {
    "freshness_policy": "explicit"
  },
  "branches": [],
  "fallback": {
    "triggered": false
  },
  "candidates": [
    {
      "name": "example-skill",
      "function_summary": "...",
      "score": 108
    }
  ]
}
```

PowerShell 兼容入口：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/recommend-skills.ps1 `
  -Query "生成一个现代 React 后台管理界面"
```

只有维护分类规则时才查看中间分类分支：

```bash
python scripts/recommend-skills.py --query "前端界面" --show-branches
```

## 索引维护

普通选择始终使用现有索引。只有本地 skill 确实变化或需要诊断时，才重新核对来源目录。

```bash
# 路由前严格核对全部根目录
python scripts/recommend-skills.py --query "健康检查" --strict-freshness

# 忽略以前的严格检查缓存
python scripts/recommend-skills.py --query "健康检查" --force-freshness-check

# 诊断已安装索引
python scripts/doctor.py

# 修复缺失、损坏、不完整或旧版本索引
python scripts/doctor.py --fix

# 强制完整重新分类
python scripts/recommend-skills.py --query "健康检查" --full-rebuild
```

PowerShell 使用 `-StrictFreshness` 显式执行全库核对。

## 本地数据

运行数据保存在已安装 skill 的 `.skill-index/` 中，不会进入发布包：

- `deep/lazy-route.sqlite3`：默认懒加载路由数据库。
- `deep/metadata.json`：协议版本、来源目录、数量和构建状态。
- `deep/source-manifest.json`：来源指纹和分类结果。
- `deep/facets.json`：可移植的分类倒排分面。
- `deep/route-cards.json`：紧凑候选卡片。
- `selection-memory.md`：隐私优先的本地排序反馈。

## 开发与验证

```bash
python tests/run-python-smoke-tests.py
powershell -ExecutionPolicy Bypass -File tests/run-smoke-tests.ps1
powershell -ExecutionPolicy Bypass -File scripts/clean-local-artifacts.ps1
powershell -ExecutionPolicy Bypass -File scripts/package-release.ps1 -Version v1.9.0
```

仓库结构：

```text
skill-selection-assistant/
|-- scripts/                         安装、清理和发布工具
|-- skill-selection-assistant/       可安装的 Codex skill
|   |-- scripts/                     分类器、路由器、诊断和记忆工具
|   |-- rules/                       共享分类规则
|   |-- schemas/                     推荐输出协议
|   `-- references/                  按需读取的维护文档
|-- tests/                           Python 与 PowerShell 冒烟测试
|-- INSTALLATION_BEHAVIOR.md         安装和可移植性约定
`-- SELF_GROWTH.md                   排序与分类自增长设计
```

## 更多文档

- [安装与本地边界](./INSTALLATION_BEHAVIOR.md)
- [自增长设计](./SELF_GROWTH.md)
- [更新记录](./CHANGELOG.md)
- [开源许可](./LICENSE)
