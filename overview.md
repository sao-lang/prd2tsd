# PRD2TSD Agents — 开发记录

### 2026-07-24

#### 3. 自动同步方案：junction + Git hooks 协同

- **时间：** 2026-07-24 13:00:00
- **发起人：** user
- **修改文件：**
  - `.github/skills/ai-coding-rules` — 替换为 Junction → `lania-shared-skills`（实时同步）
  - `.github/skills/debug-tools` — 替换为 Junction → `lania-shared-skills`（实时同步）
  - `.githooks/pre-commit` — 重写，提交前：拆 junction → 复制真实文件 → clear skip-worktree → git add
  - `.githooks/post-commit` — 新增，提交后：删真实文件 → 重建 junction → set skip-worktree
  - `.githooks/post-checkout` — 更新，检出后检测异常状态并恢复 junction
  - `sync-skills.ps1` — 重写，支持三种模式：默认/ToReal/ToJunction
- **修改内容：** 最终方案：开发时用 junction 实时同步共享目录更改 + skip-worktree 让 Git 忽略；提交时 pre-commit 自动转真实文件让 Git 感知改动并加入提交；提交后 post-commit 自动恢复 junction。
- **复盘结果：**
  - ✅ 日常改共享目录 → 项目实时同步（junction）
  - ✅ `git status` 日常不显示 junction 文件（skip-worktree）
  - ✅ `git commit` → pre-commit 自动转真实文件 → Git 感知改动 → 提交 → post-commit 恢复 junction
  - ✅ 手动切换：`.\sync-skills.ps1 -ToReal` / `-ToJunction`
  - ✅ `lania-agent-runtime` 非 Git 项目，junction 全自动

#### 2. Skill 规则合并至共享目录 + Git 兼容方案

- **时间：** 2026-07-24 12:30:00
- **发起人：** user
- **修改文件：**
  - `E:\vsc-workspace\lania-shared-skills\ai-coding-rules\` — 合并所有改动至共享中心
  - `E:\vsc-workspace\lania-shared-skills\sync-to-project.ps1` — 新增同步脚本
  - `prd2tsd-agents\.github\skills\ai-coding-rules` — 恢复为真实目录（Git 兼容），通过 `sync-to-project.ps1` 与共享目录同步
  - `lania-agent-runtime\.github\skills\ai-coding-rules` — Junction → `lania-shared-skills`（非 Git 项目，junction 自动同步）
  - `lania-agent-runtime\.github\copilot-instructions.md` — 新建
- **修改内容：** 共享目录合并完成后，发现 prd2tsd-agents 用 Junction 会导致 Git 显示文件被删除。已将 prd2tsd-agents 恢复为真实文件目录，新增 `sync-to-project.ps1` 同步脚本用于手动从共享目录同步到各项目
- **修改内容：** 将四层测试体系、真实环境验证、验证报告模板等改动合并到共享目录 `lania-shared-skills`；prd2tsd-agents 的 ai-coding-rules 从独立副本改为 Junction 链接，修改共享目录即自动同步所有项目
- **复盘结果：** 双向合并完成——共享目录获得了新规则（R10a/四层测试/验证报告），prd2tsd-agents 获得了共享目录的已有改进（R8b/R8c 设计文档 checklist、R10 功能可用性验证、各语言注释示例）
- **潜在风险：** 修改共享目录会影响所有通过 Junction 链接的项目，改动前需确认影响范围

#### 4. 批量部署 skills 同步到 lania-zip 全部 14 个项目

- **时间：** 2026-07-24 13:30:00
- **发起人：** user
- **修改文件：**
  - `lania-shared-skills\setup-all-projects.ps1` — 新增批量安装脚本
  - 13 个项目（除 prd2tsd-agents 外）安装了 `.githooks/` + `sync-skills.ps1`
- **修改内容：** 通过 `setup-all-projects.ps1` 一键为所有项目配置：.githooks（pre-commit / post-commit / post-checkout）、sync-skills.ps1、git config core.hooksPath、git update-index --skip-worktree
- **复盘结果：** 全部 14 个项目统一完成配置。修改共享目录后，任一项目执行 git commit 自动同步 → Git 感知改动 → 提交后恢复 junction 实时同步
- **潜在风险：** setup-all-projects.ps1 仅在新增项目时需要重新执行

#### 1. Skill 规则增强：强制真实环境连接验证（Smoke Test）

- **时间：** 2026-07-24 12:00:00
- **发起人：** user
- **修改文件：**
  - `.github/skills/ai-coding-rules/rules/00-base.instructions.md` — 新增 R10a 真实环境验证规则
  - `.github/skills/ai-coding-rules/rules/03-testing.instructions.md` — 重写为测试分层规范，增加 Smoke Test 强制要求
  - `.github/skills/ai-coding-rules/rules/01-typescript.instructions.md` — Testing 节增加真实环境验证
  - `.github/skills/ai-coding-rules/rules/08-dart.instructions.md` — Testing 节增加真实环境验证
  - `.github/skills/ai-coding-rules/rules/09-rust.instructions.md` — Testing 节增加真实环境验证
  - `.github/skills/ai-coding-rules/rules/10-python.instructions.md` — Testing 节增加真实环境验证
  - `.github/skills/ai-coding-rules/rules/11-go.instructions.md` — Testing 节增加真实环境验证
- **修改内容：** 新增全局规则 R10a，要求涉及外部服务的项目必须运行真实环境连接验证测试（禁止 Mock），确认服务可达后才能报告"测试通过"；03-testing 重写为四层测试体系（单元/集成/Smoke/E2E）；新增"验证报告"强制输出章节（含标准模板，必须按格式输出测试结论）；所有语言规则同步增加真实环境验证要求；E2E 测试通过为最终准入条件
- **复盘结果：** 解决了 AI 仅凭 Mock 测试通过就误报"全部成功"的问题，现在 Skill 强制要求：(1) 区分 Mock 测试与真实环境测试 (2) 测试结束后必须按模板输出结构化验证报告 (3) 所有外部服务 Smoke Test 必须 ✅ 正常 (4) 有完整环境时还需 E2E 测试通过才能报告"通过"
- **潜在风险：** 部分 CI/CD 环境可能没有外部服务运行中，需要配置条件跳过或标记为"环境不可用"

### 2026-07-23

#### 1. 块 A：基础设施与质量底座

- **时间：** 2026-07-23 14:30:00
- **发起人：** user
- **修改文件：**
  - 新增 42 个文件（见下方详表）
- **修改内容：** 搭建项目骨架、质量基础设施、数据模型、认证授权和多租户中间件、LLM Gateway 核心、模型配置中心、数据安全模块、CI/CD 流水线
- **复盘结果：** 所有基础设施容器（PostgreSQL/Redis/MinIO/Neo4j）正常运行，52 个单元测试通过，E2E 全链路 12/12 通过
- **潜在风险：** Neo4j 需企业版镜像，当前使用社区版；passlib 在 Python 3.14 不兼容，已改用 bcrypt 直接调用

**新增文件清单：**

```
├── pyproject.toml / requirements.txt / .gitignore
├── docker-compose.yml / Dockerfile
├── contracts/ (__init__, interfaces, models)
├── app/
│   ├── main.py
│   ├── core/ (config, connections, llm, logger, exceptions)
│   ├── llm_gateway/ (__init__, models, config_manager, provider, router, cost_tracker, cache)
│   ├── security/ (data_classifier, data_masking, audit_logger)
│   ├── models/ (base, user, organization, workspace, role, team_member)
│   ├── auth/ (token_manager, permissions, middleware, deps)
│   └── api/ (deps, routes/auth/workspace/model_config, schemas)
├── .github/workflows/ (ci, deploy-prod, backup)
├── alembic/ (env, script.py.mako)
├── scripts/ (init_db, e2e_test, ensure_tables, debug_login)
├── tests/ (conftest, 14 test files)
├── overview.md

### 2026-07-23

#### 2. 块 B：知识层（数据 + 检索）

- **时间：** 2026-07-23 18:30:00
- **发起人：** user
- **修改文件：**
  - `requirements.txt` — 新增 llama-index-core, llama-index-graph-stores-neo4j, llama-index-vector-stores-postgres, llama-index-embeddings-huggingface, sentence-transformers, pgvector
  - 新增 `app/knowledge_layer/` (24 个文件)
- **修改内容：** 构建知识图谱完整生命周期：模型定义 → 文档加载 → 多粒度分块 → LLM 实体/关系提取 → 实体融合/消歧 → Claims 提取 → 多源融合 Embedding → TextUnit 构建 → Neo4j/PGVector 双写 → 版本控制/快照 → 知识老化策略 → 检索管线（意图路由/重写/丰富/Local Search/Global Search/RRF 融合/重排/压缩）
- **复盘结果：** 79 个单元测试通过（含块 A 回归测试全绿），7 个集成测试通过（Mock 模式）
- **潜在风险：** BGE Embedding 模型首次加载较慢（~3min）；Neo4j/PGVector 集成测试需真实容器运行

#### 3. 块 B ↔ 块 A 联通性打通

- **时间：** 2026-07-23 20:00:00
- **发起人：** user
- **修改文件：**
  - `app/core/connections.py` — Neo4jConnector enabled=False → True（启动时自动连接）
  - `.env` — DATABASE_URL/NEO4J_URI 修复为 localhost
  - `app/api/routes/knowledge.py` — 新增（build / search 两个端点）
  - `app/main.py` — 挂载 knowledge_routes，注册知识层 API
  - `requirements.txt` — 新增 python-multipart
  - `scripts/e2e_test.py` — 扩展 2 个知识层测试步骤
- **修改内容：** 打通块 B 知识层与块 A 基础设施的全链路集成：Neo4j 启动时自动连接、知识层 API 路由挂载（Auth 中间件保护）、健康检查纳入 Neo4j 状态
- **复盘结果：**
  - E2E 14/14 ✅（块 A 12 项 + 块 B 2 项）
  - 单元测试 79/79 ✅（含全部块 A 回归）
  - 集成测试 7/7 ✅
  - Ruff 0 errors ✅
  - Neo4j 连接: `connected=true, latency=5ms`
  - PostgreSQL 连接: `connected=true, latency=6ms`
- **潜在风险：** mypy strict 模式在 `connections.py` 有 11 个已有类型错误（块 A 遗留）；知识层搜索 API 涉及 LLM 调用导致首次响应较慢

**新增文件清单：**

```
app/knowledge_layer/
├── __init__.py / config.py / models.py / pipeline.py
├── graph_store.py / vector_store.py
├── ingestion/
│   ├── __init__.py / document_loader.py / chunker.py
│   ├── entity_extractor.py / relation_extractor.py / entity_resolver.py
│   ├── claims_extractor.py / entity_embedder.py / text_unit_builder.py
│   ├── knowledge_aging.py / kg_versioning.py / index_builder.py
└── retrieval/
    ├── __init__.py / intent_router.py / rewriter.py / enricher.py
    ├── local_search.py / global_search.py / fusion.py / reranker.py / compressor.py

tests/
├── fixtures/sample_prd.md
├── unit/
│   ├── test_ingestion.py / test_entity_resolver.py / test_claims_extractor.py
│   ├── test_knowledge_aging.py / test_kg_versioning.py
│   └── test_local_search.py / test_global_search.py
└── integration/
    ├── test_kg_build.py / test_kg_versioning_integration.py
    ├── test_local_search_integration.py / test_global_search_integration.py
```
