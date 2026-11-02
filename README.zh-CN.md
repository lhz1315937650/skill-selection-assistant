# Skill Selection Assistant

[![Release](https://img.shields.io/github/v/release/lhz1315937650/skill-selection-assistant)](https://github.com/lhz1315937650/skill-selection-assistant/releases)
[![Tests](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml/badge.svg)](https://github.com/lhz1315937650/skill-selection-assistant/actions/workflows/smoke-tests.yml)
[![License](https://img.shields.io/github/license/lhz1315937650/skill-selection-assistant)](./LICENSE)

中文 | [English](./README.md)

面向大型 Codex skill 库的本地选择器。它会先缩小请求范围，再返回最合适的几个 skill，不会扫描全部源 `SKILL.md`。

## 工作机制

1. **识别请求**：分析项目上下文、任务意图、领域和技术栈。
2. **按标签取数**：只加载命中标签的 skill 卡片。
3. **懒加载短名单**：只给高权重候选，其他 skill 保持不处理。
4. **评分排序**：结合标签、正向示例和反向示例筛选候选结果。
5. **兜底召回**：分类命中较弱时，使用 SQLite FTS5/BM25 进行全文召回和重排。
6. **返回最终结果**：只给出最匹配的几个 skill，不要求用户逐分类选择。

```text
请求 -> 上下文 -> 标签查询 -> 懒加载 -> 评分排序 -> BM25 兜底 -> 最终 skill
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

推荐短名单：

```bash
python scripts/recommend-skills.py \
  --query "生成一个现代 React 后台界面" \
  --compact
```

新增一条 skill 时只插入这一条，不扫描整个库：

```bash
python scripts/ingest-skill.py --skill-md path/to/SKILL.md
python scripts/ingest-skill.py --list-pending --skills-root path/to/skills
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
# 知识库增强（P0–P4）

在保留原有 SQLite 多标签路由、渐进式加载和反馈记忆的基础上，现已加入三项可选能力：

- `scripts/document-ingest.py`：将 Markdown/TXT 以及可选 PDF/DOCX 内容统一规范化为文档源包。
- `scripts/rag-index.py`：构建零额外依赖的轻量向量索引（中文/英文 token + 字符二元组），支持语义近似召回；未来可替换为外部 embedding 后端。
- `scripts/wiki-generate.py`：从 SQLite 索引生成离线 HTML 技能目录、详情页、分类信息和浏览器端搜索。
- `scripts/evaluate-retrieval.py`：基于标注查询集计算命中率与 MRR@5。

示例：

```powershell
python skill-selection-assistant/scripts/recommend-skills.py `
  --query "构建一个现代后台管理界面" `
  --rag `
  --wiki-output .skill-index/wiki

python skill-selection-assistant/scripts/document-ingest.py `
  --source .\my-notes `
  --output .skill-index/documents.json

python skill-selection-assistant/scripts/rag-index.py `
  --index-dir .skill-index `
  --source .\my-notes
```

RAG 与 Wiki 都是增强层：默认路由行为不变，`--rag` 才会追加向量召回结果；`--wiki-output` 只生成静态呈现层，不把页面内容注入路由上下文。

如需接入 OpenAI-compatible 解释服务，可显式传入 `--explain-api-url`；未提供时始终使用本地确定性解释，不读取或猜测用户密钥。
