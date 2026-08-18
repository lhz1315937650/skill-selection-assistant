# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![Tests](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

中文 | [English](./README.md)

一个面向大型 Codex skill 库的本地快速选择器。

它在构建索引时完成分类，结合当前项目上下文查询相关分类，并只返回最终候选。普通请求不会扫描全部源 `SKILL.md`。

## 核心能力

- 根据项目身份和技术栈补充上下文。
- 使用正例和反例明确 skill 边界。
- 通过 SQLite 懒加载当前分类路径。
- 弱命中时使用 BM25 召回与重排兜底。
- 全程本地运行，不需要 Embedding API 或额外模型。

## 工作流程

```text
项目上下文
    -> 分层 skill 画像
    -> 分类路由
    -> 召回与重排兜底
    -> 最终候选
```

## 安装

要求 Python 3.10+。

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

结果会包含最终加权 skill、分类路径、项目上下文和兜底状态。

## 维护

```bash
# 检查索引
python scripts/doctor.py

# 修复或重建索引
python scripts/doctor.py --fix

# 运行测试
python tests/run-python-smoke-tests.py
powershell -ExecutionPolicy Bypass -File tests/run-smoke-tests.ps1
```

本地索引保存在 `.skill-index/`，不会进入发布包。

## 许可

[MIT](./LICENSE)
