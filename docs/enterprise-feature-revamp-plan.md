# 块 E 企业级功能整改实现方案

> **产出日期**：2026-08-13
> **依据**：逐文件审计 `app/` 下块 E 相关模块（CSV 索引 / 多模态 / 协作文档 / 搜索回退 / 交互接口 / 意图识别），结论已与用户逐条确认
> **核心目标**：① 删除 4 个"半实现/假实现/有安全风险"的企业级功能 ② 将 对话/提问/文档生成 合并为**单一统一入口**，服务端按意图识别分流 ③ 补齐 URL 文档上传分析能力 ④ **多格式文档（pdf/csv/docx/md/txt/png/jpg）上传后自动构建知识图谱**
> **状态**：方案待用户确认后进入实现

---

## 一、背景与现状（审计结论）

经逐文件核实，块 E 现有实现存在以下问题：

| # | 功能 | 现状核实 | 判定 |
|---|------|---------|------|
| 1 | **CSV 双通路索引 (E6)** | `CsvDualPathIndexer` 已接入上传流程（`documents.py:273`、`service.py`），但**列级 Embedding 未实现**（`_analyze_columns` 只生成类型/非空数 profile），且 `upload()` 中算出的 `text_units/column_profiles` **被直接丢弃**，未写入知识图谱/PGVector → CSV 内容实际**不可检索** | 半实现 |
| 2 | **CLIP 多模态/以图搜图 (E8)** | `clip_encoder.py` 为**占位实现**（docstring 自述"返回随机向量"），真实模型需 `torch+transformers`（数 GB）；PRD→TSD 场景以文本为主、无图片语料库，以图搜图无实际价值；`grill-self-review.md` 亦标记"CLIP 与 Gateway 路由功能重复" | 占位 + 场景无意义 |
| 3 | **协作文档 (E9)** | `comment.py`/`suggestion.py`/`changelog.py` 全部**内存 dict 存储**（"重启后数据丢失"）；且"选中段落→行内评论→建议修改→回滚"需要可编辑文档模型，而生成结果是结构化数据，无真实可注释载体 | 假实现 |
| 4 | **搜索引擎回退 (E11)** | 已接入 `knowledge_layer/pipeline.py:333`（本地结果 <3 自动触发）：① 内部 query 外发到 **DuckDuckGo**（数据外泄）；② `search_and_index` 把外部结果**实时索引进内部 PGVector**（知识库污染，后续被当作内部上下文返回） | 有安全风险 |
| 5 | **交互接口分散** | 对话/提问/文档生成分属 5+ 个端点（`/chat`、`/generate`、`/qna/stream`、`/generate/stream`、`/tasks/{id}`），前端需对接多个接口；意图识别只在 `/chat` 内 | 设计缺陷 |
| 6 | **URL 文档上传** | `documents.py` 仅接受 `UploadFile`；`WebLoader.fetch()` 已具备 URL→Markdown 能力，但**未接入文档管理/分析管道**（不建文档记录、不进实体抽取/KG 写入） | 功能缺失 |
| 7 | **多格式入图 / 自动入图** | `DocumentLoader` 仅支持 `.md`（`SUPPORTED_EXTENSIONS={".md"}`）；PDF 预览为**占位**（只显示大小，无文本解析）；`app/document_management/` **完全不调用** `KnowledgeGraphBuilder`，上传文档**不会自动入图**，需另调 `/knowledge/build`；`requirements.txt` **无 PDF 解析库**（pypdf/pdfplumber 均缺失）；`python-docx` 仅用于导出未用于读取 | 功能缺失 |

---

## 二、整改目标

| 目标 | 衡量标准 |
|------|---------|
| 移除无价值/有风险的伪功能 | 上述 4 项代码、路由、测试、文档引用全部清理，`grep` 无残留 |
| 单一交互入口 | 前端仅连接**一个端点**即可完成 对话 / 提问 / 文档生成 / 文档分析，服务端按意图识别分流 |
| URL 文档可分析 | 用户传 URL → 抓取 → 建文档记录 → 入库检索（可选一键生成） |
| 多格式构建 + 自动入图 | 上传 pdf/csv/docx/md/txt/png/jpg 后**自动进入知识图谱**，`processing_status` 跟踪（pending→processing→indexed/failed） |
| 回归全绿 | 块 A/B/C/D/E 保留功能测试全通过，`test_tech_stack_compliance` 通过，无 TODO 残留 |

---

## 三、修改方案总览

```
A. 删除类（4 项，整体移除）
   A1. CSV 双通路索引（E6）
   A2. CLIP 多模态/以图搜图（E8）
   A3. 协作文档（E9）
   A4. 搜索引擎回退（E11）

B. 新增/重构类（核心）
   B1. 统一交互入口（合并 对话/提问/文档生成 + 文档分析）← 核心
   B2. URL 文档上传分析（并入 B1 的 document_analysis 意图）
   B3. 多格式知识图谱构建 + 上传自动入图（pdf/csv/docx/md/txt/png/jpg）← 新需求

C. 保留不动
   E1 LLM Gateway / E2 观测性 / E3 会话历史 / E4 文档管理（文件上传部分）
   E5 Webhook / E7 Web 资源索引（URL 抓取/爬虫/同步）/ E10 批量任务 / E12 SSE
```

---

## 四、A 类：删除项明细

### A1. 删除 CSV 双通路索引（E6）

| 类型 | 内容 |
|------|------|
| 代码 | 删 `app/document_management/csv_loader.py`；`service.py` 移除 `csv_indexer` 注入 + upload 中 `csv/tsv` 索引分支；`documents.py:273` 移除 CSV 索引调用；`document_management/__init__.py` 移除导出 |
| 保留 | `.csv/.tsv` 仍可上传 / 存储 / 预览 / 按文件名搜索（仅不做内容索引） |
| 测试 | 删 `tests/unit/test_document_management.py::TestCsvDualPathIndexer`、`tests/integration/test_csv_indexing.py`（如存在） |
| 文档 | `docs/block-E-enterprise.md` E6、`docs/full-architecture-deep-dive.md`、`overview.md` |
| 影响 | CSV 内容不再进入检索；上传链路其余部分不变 |

### A2. 删除 CLIP 多模态/以图搜图（E8）

| 类型 | 内容 |
|------|------|
| 代码 | 删 `app/multimodal/` 整目录（clip_encoder / image_chunk_store / multimodal_search / image_preview） |
| 路由 | 删 `app/api/routes/multimodal.py`、`main.py` 注册、`schemas/multimodal.py`、`schemas/__init__.py` 导出 |
| Capability | 评估删 `app/llm_gateway/capabilities/image_encoder.py`（CLIP capability）及 `gateway.encode_image` 相关引用 |
| 测试 | 删 `tests/unit/test_multimodal.py`、`tests/integration/test_multimodal_search.py` |
| 依赖 | Pillow 目前仅 `image_preview` 使用，删除后确认无其他引用则从 `requirements.txt` 移除；`torch/transformers` 因 reranker/reranking 保留 |
| 文档 | `docs/block-E-enterprise.md` E8、`docs/full-architecture-deep-dive.md`、`overview.md`、`.env.example`（`IMAGE_ENCODE_MODE` 等） |

### A3. 删除协作文档（E9）

| 类型 | 内容 |
|------|------|
| 代码 | 删 `app/collaboration/` 整目录（comment / suggestion / changelog / models / service） |
| 路由 | 删 `app/api/routes/collaboration.py`、`main.py` 注册、`schemas/collaboration.py`、`schemas/__init__.py` 导出 |
| 测试 | 删 `tests/unit/test_collaboration.py`、`tests/integration/test_collaboration_flow.py` |
| 影响 | **无数据库表**（纯内存），无需迁移清理 |
| 文档 | `docs/block-E-enterprise.md` E9、`docs/full-architecture-deep-dive.md`、`overview.md` |

### A4. 删除搜索引擎回退（E11）

| 类型 | 内容 |
|------|------|
| 代码 | 删 `app/web_indexing/search_fallback.py`；`web_indexing.py` 移除 `/search-fallback` 端点；`schemas` 移除 `SearchFallbackResult` |
| 关键 | **移除 `knowledge_layer/pipeline.py:333` 附近自动回退段**（本地结果 <3 时触发网络搜索 + 索引）——安全风险核心 |
| 测试 | 删 `tests/integration/test_search_fallback.py`、`tests/unit/test_web_indexing.py::TestSearchFallback` |
| 行为变化 | 本地检索不足时返回"无结果"，不再外泄内部 query、不再污染知识库 |
| 文档 | `docs/block-E-enterprise.md` E11、`docs/full-architecture-deep-dive.md`、`overview.md` |

---

## 五、B 类：统一交互入口设计（核心）

### 5.1 端点与请求/响应模型

**新增唯一交互端点：`POST /api/v1/interact`**

```python
# app/api/schemas/interact.py
class InteractRequest(BaseModel):
    message: str                      # 用户输入（对话/提问/PRD 内容/分析指令）
    session_id: str = ""
    workspace_id: str = ""
    stream: bool = False              # true → SSE 流式返回
    # 文档类意图可选输入
    doc_id: str = ""                  # 对已上传文档提问/分析
    url: str = ""                     # 对 URL 分析/生成
    prd_type: str = "md"              # 生成意图：PRD 类型（md/pdf/docx/txt）


class InteractResponse(BaseModel):
    intent: str                       # 识别到的意图
    confidence: float
    message: str                      # 回答文本（同步模式）
    task_id: str = ""                 # complex_generation 同步模式返回任务 ID
    session_id: str = ""
```

**流式模式**：`stream=true` 时返回 `text/event-stream`，复用现有 E12 EventBus / `gateway.stream_complete()`，事件类型沿用 `task.* / generation.* / qna.*`。

### 5.2 意图识别与路由表

复用并扩展 `IntentClassifier`（规则 + LLM 两级），新增 `document_analysis` 意图：

| 意图 | 触发示例 | 处理节点 | 同步模式 | 流式模式 |
|------|---------|---------|---------|---------|
| `chat` | 你好 / 谢谢 | `ChatNode` | 直接返回文本 | SSE `qna.chunk` |
| `knowledge_qa` | "XX 是什么" / "文档里怎么说"（可带 `doc_id`） | `KnowledgeQANode`（知识检索+回答） | 返回文本 | SSE `qna.status/chunk` |
| `document_analysis` | 带 `url` 或 `doc_id` + 分析指令 | 抓取/读取 → 分析 → 入库（见 5.5） | 返回分析摘要 | SSE 逐阶段推送 |
| `complex_generation` | "生成技术方案" / PRD 内容 | 创建异步任务 → 全链路生成 | 返回 `task_id` | SSE `task.* / generation.*` 全程推送 |
| `clarification` | 信息不足 | `ClarifyNode` | 返回追问 | SSE |

### 5.3 消除"双实现"（路由手动分类 vs 图内 classify 节点）

**现状问题**：`chat.py` 路由手动 `classifier.classify()` 一次，随后图内 `classify` 节点又分类一次，两处判定存在不一致风险。

**修订方案**：

```
统一交互入口（app/api/routes/interact.py）
  1. 调用共享 IntentClassifier（单例）→ 得 intent
  2. 按 intent 决定执行模式：
     - chat / knowledge_qa / clarification → 调主编排图（图内 classify 节点改为
       "state 已有 intent 则跳过分类"，保证只分类一次）
     - document_analysis → 调文档分析服务（或作为图内新节点）
     - complex_generation → 创建异步任务（同步模式返回 task_id）
  3. stream=true 时统一走 SSE
```

**要点**：`IntentClassifier` 收敛为单一判定来源；图内 `classify` 节点改为**幂等**（检测 `state["intent"]` 已存在则直接复用），消除重复分类。

### 5.4 旧端点处置（需确认）

| 端点 | 处置建议 |
|------|---------|
| `POST /api/v1/chat` | 移除，由 `/interact` 替代 |
| `POST /api/v1/generate` | 移除，由 `/interact` 的 `complex_generation` 意图替代 |
| `POST /api/v1/qna/stream` | 移除，由 `/interact?stream=true` 的 `knowledge_qa` 意图替代 |
| `POST /api/v1/generate/stream` | 移除，由 `/interact?stream=true` 的 `complex_generation` 意图替代 |
| `GET /api/v1/tasks/{task_id}` | **保留**（任务状态/结果查询） |

### 5.5 URL 文档上传分析（B2，并入 `document_analysis` 意图）

```
POST /interact  { message: "分析这个 URL", url: "https://...", intent: document_analysis }
  → URL 校验（协议 http/https，防 SSRF 内网地址）
  → WebLoader.fetch(url) → Markdown（复用 app/web_indexing/web_loader.py）
  → 创建 uploaded_documents 记录（source_url 字段已存在 ✓，file_type="url"，storage 存 Markdown）
  → 复用块 B 分析管道：分块 → 实体抽取 → 知识图谱写入
  → 返回分析摘要（可选：一键生成 TSD → 转 complex_generation）
```

**待决策**：抓取后默认入库检索；是否支持"一键生成 TSD"开关（`generate=true`）。

---

## 5.6 多格式知识图谱构建 + 上传自动入图（B3，新需求）

> **需求**：上传 pdf / csv / docx / md / txt / png / jpg 等常用格式后**自动构建知识图谱**，无需手动调 `/knowledge/build`。

### 5.6.1 多格式文本提取（bytes → text）

新增 `app/knowledge_layer/ingestion/multi_format_loader.py`：

| 格式 | 提取方法 | 依赖 |
|------|---------|------|
| `.md` / `.txt` | UTF-8 解码 | 无 |
| `.csv` / `.tsv` | csv 标准库，每行转自然语言句子（**仅行级文本转换**，不做已删除的"列级 Embedding 双通路"） | 标准库 |
| `.docx` | `python-docx` 读取段落 + 表格（依赖已存在，现仅用于导出） | python-docx |
| `.pdf` | `pypdf` 逐页提取文本（**新增依赖**） | pypdf>=4.0 |
| `.png` / `.jpg` / `.jpeg` | 图片无文本 → **元数据占位 chunk**（`[图片: 文件名, 类型, 大小]`，可被文件名检索）；不引入重型视觉方案（与已删除的 CLIP 一致） | 无 |

### 5.6.2 构建入口扩展

`KnowledgeGraphBuilder` 新增 `build_from_bytes(content, filename, workspace_id)`：内部用 `multi_format_loader` 提取文本 → 复用现有 `build_from_text()` 链路（分块 → 实体提取 → 消歧 → Neo4j → PGVector）。

### 5.6.3 上传自动入图

- 挂接点：`app/document_management/service.py::upload()` —— MinIO 存储 + DB 记录后，若文件类型在可索引集合内，**异步触发** KG 构建
- 异步机制（待决策）：
  - 方案一（推荐）：**Celery 任务** `index_document_to_kg`（可靠/可重试/可监控，复用 E10 基础设施）
  - 方案二：`asyncio.create_task`（开发简单，进程重启丢失、无重试）
- 状态跟踪：复用 `uploaded_documents.processing_status`（pending / processing / indexed / failed）+ `processing_error`，前端轮询 `GET /documents/{id}`
- URL 文档（B2）抓取成功后同样自动入图，两条链路统一

### 5.6.4 文件清单

```
新增: app/knowledge_layer/ingestion/multi_format_loader.py
新增: app/batch/tasks.py::index_document_to_kg（Celery 方案）
修改: app/knowledge_layer/pipeline.py（build_from_bytes）
修改: app/document_management/service.py（upload 后异步触发）
修改: app/document_management/models.py（如需补充状态）
新增: requirements.txt pypdf>=4.0
测试: tests/integration/test_kg_build_multi_format.py
```

---

## 六、实施清单（R8b checklist）

> 以下清单待用户确认后逐项实现，每完成一项标记 `[x]`。

### P0 — 删除类（A1–A4）

- [ ] A1 删除 CSV 双通路索引（代码/路由/导出/测试/文档）
- [ ] A2 删除 CLIP 多模态（模块/路由/schema/capability/测试/依赖评估/文档）
- [ ] A3 删除协作文档（模块/路由/schema/测试/文档）
- [ ] A4 删除搜索回退（模块/路由/schema/`pipeline.py` 自动回退段/测试/文档）

### P1 — 统一交互入口（B1）

- [ ] 新增 `app/api/schemas/interact.py`（请求/响应模型）
- [ ] 扩展 `IntentClassifier`：新增 `document_analysis` 意图 + 规则/LLM 分类
- [ ] 图内 `classify` 节点改为幂等（state 已有 intent 则跳过）
- [ ] 新增 `app/api/routes/interact.py`：统一分发（chat / knowledge_qa / document_analysis / complex_generation / clarification）+ 同步/流式双模式
- [ ] `app/main.py`：注册 `/interact`，移除旧端点注册（`/chat`、`/generate`、`/qna/stream`、`/generate/stream`）
- [ ] 保留 `GET /tasks/{id}` 任务查询

### P2 — URL 文档分析（B2）

- [ ] 新增 URL 抓取入库服务（复用 `WebLoader`，建文档记录，走块 B 管道）
- [ ] 接入 `document_analysis` 意图处理链路
- [ ] SSRF 防护（协议白名单 + 内网地址拦截 + 超时/大小限制）

### P2.5 — 多格式构建 + 自动入图（B3）

- [ ] 新增 `multi_format_loader.py`：md/txt/csv/docx/pdf 文本提取 + 图片元数据占位
- [ ] `requirements.txt` 新增 `pypdf>=4.0`（PDF 解析）
- [ ] `KnowledgeGraphBuilder.build_from_bytes()` 扩展
- [ ] `service.py::upload()` 上传后异步触发入图（Celery 或 asyncio）
- [ ] `processing_status` 状态跟踪 + 失败记录 `processing_error`
- [ ] 测试：`tests/integration/test_kg_build_multi_format.py`

### P3 — 验证与文档

- [ ] 新增测试：`tests/unit/test_interact.py`、`tests/integration/test_interact_flow.py`、`tests/integration/test_url_document.py`
- [ ] 更新 `docs/block-E-enterprise.md`（移除 E6/E8/E9/E11 章节；新增统一入口 + URL 文档章节）
- [ ] 更新 `docs/full-architecture-deep-dive.md`、`overview.md`、`.env.example`
- [ ] 全量回归：`mypy app/ --strict --ignore-missing-imports` + `ruff check app/ tests/` + `pytest tests/ -v --tb=short`
- [ ] 无 TODO 残留：`grep -rn "TODO\|FIXME\|NotImplementedError" app/ --include="*.py"`

---

## 七、测试计划

| 类别 | 内容 |
|------|------|
| 单元 | `test_interact.py`（意图分流/幂等 classify/模型校验）、`test_url_document.py`（URL 校验/SSRF/入库）、`test_multi_format_loader.py`（各格式提取正确性） |
| 集成 | `test_interact_flow.py`（对话→提问→生成 三意图全流程）、`test_url_document.py`（抓取→入库→检索）、`test_kg_build_multi_format.py`（上传→自动入图→可检索） |
| 回归 | 全量 `pytest tests/ -v`，确认块 A/B/C/D/E 保留功能仍全绿 |
| 环境 | `pytest tests/e2e/test_full_flow.py -v --slow`（端到端） |

---

## 八、风险与待决策点

| # | 待决策 | 建议 |
|---|--------|------|
| 1 | 统一入口命名：`/api/v1/interact` vs 复用 `/chat` 升级 | 新增 `/interact` |
| 2 | 旧端点移除 vs 保留兼容 | 移除（前端只连 `/interact`） |
| 3 | 流式模式是否首期实现 | 首期实现（生成长任务必需） |
| 4 | URL 文档：仅入库检索 vs 支持一键生成 TSD | 默认入库检索 + `generate=true` 开关 |
| 5 | 删除项是否同步清理依赖（Pillow / IMAGE_ENCODE_MODE） | 确认无引用后清理 |
| 6 | 删除后原 `/chat` 已有客户端兼容 | 文档标注升级路径 |
| 7 | **PDF 解析库**：`pypdf`（轻量，推荐）vs `pdfplumber`（表格提取更好） | `pypdf>=4.0` |
| 8 | **图片入图方式**：A 元数据占位（推荐）/ B Vision LLM 描述 / C OCR | 默认 A，不引入重型视觉方案 |
| 9 | **异步机制**：Celery（可靠/可重试，推荐）vs `asyncio.create_task`（开发简单） | Celery（生产），开发可降级 asyncio |

**风险提示**：
- 统一入口改动面较大，涉及 `main.py` 路由注册与意图链路，需保证 `complex_generation` 异步化不回归
- `pipeline.py` 移除回退段后，本地检索不足时回答质量依赖 `knowledge_qa` 的"无结果直接回答"降级路径（已有）
- 删除大量测试文件后需同步更新 `tests/conftest.py` 或相关 fixture 引用
