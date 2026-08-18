# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![Tests](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

中文 | [English](./README.md)

面向大型 Codex skill 库的本地选择器。它会先缩小请求范围，再返回最合适的几个 skill，不会扫描全部源 `SKILL.md`。

## 工作机制

1. **识别请求**：分析项目上下文、任务意图、领域和技术栈。
2. **分层分类**：按领域、专业方向、任务类型和技术栈逐步路由。
3. **懒加载**：只加载当前分类对应的索引和候选 skill，其他分类保持不处理。
4. **评分排序**：结合标签、正向示例和反向示例筛选候选结果。
5. **兜底召回**：分类命中较弱时，使用 SQLite FTS5/BM25 进行全文召回和重排。
6. **返回最终结果**：只给出最匹配的几个 skill，不要求用户逐分类选择。

```text
请求 -> 上下文 -> 分类路由 -> 懒加载 -> 评分排序 -> BM25 兜底 -> 最终 skill
```

## 核心能力

- SQLite 懒加载，适用于大型 skill 库。
- 结合项目上下文进行分类。
- 支持正向示例和反向示例。
- BM25 召回与重排兜底。
- 全程本地运行，无需 Embedding API 或额外模型。

## 安装

需要 Python 3.10+。

```bash
git clone https://github.com/lhz1315937650/skill-selection-assistant.git
cd skill-selection-assistant
python scripts/install-skill.py --configure-agents
```

更新已有安装：

```bash
python scripts/install-skill.py --force
```

## 使用

```bash
python scripts/recommend-skills.py \
  --query "生成一个现代 React 后台界面" \
  --compact
```

## 维护

```bash
python scripts/doctor.py
python scripts/doctor.py --fix
python tests/run-python-smoke-tests.py
```

本地索引保存在 `.skill-index/`，不会打包进发布文件。

## 许可证

[MIT](./LICENSE)
