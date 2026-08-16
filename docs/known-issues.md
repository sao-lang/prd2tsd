# 已知问题基线清单（known-issues）

> 按 [plan-cr-mechanism.md](./plan-cr-mechanism.md) 第 2.2 节建立，格式：`问题 | 关联测试 | 状态 | 修复记录`。
> 机器校验规则：标记"已修复"的问题，关联测试必须存在且通过；标记"未修复"的问题必须仍存在。

## 存量基线（Phase 0 采集，2026-08-15）

| 问题 | 关联测试 / 复现命令 | 状态 | 修复记录 |
|------|---------------------|------|----------|
| ruff 违规（采集时 6 条；历史基线 37 条） | `ruff check app/ tests/ contracts/` | ✅ 已修复 | Phase 1 清零，含未用导入/三元表达式/行超长/冗余测试 |
| mypy 违规 205 条（72 文件，dict/StateGraph 泛型、no-any-return、attr-defined 为主） | `mypy app/ contracts/ --strict --ignore-missing-imports` | ✅ 已修复 | Phase 1 清零，266 文件 0 错误 |
| test_batch 依赖 Redis broker，无 Redis 时失败 | `tests/unit/test_batch.py::TestBatchScheduler::test_trigger_known_task` | ✅ 已修复 | 本地以真实 Redis（localhost:6379）覆盖 `REDIS_URL`；CI test job 增加 redis service |
| test_ingestion tmp_path 权限错误（Windows 环境） | `tests/unit/test_ingestion.py::TestDocumentLoader` | ✅ 已修复 | 本地 TMP/TEMP 指向工作区可写目录；CI（Linux）无此问题 |
| test_lint 缺 docstring 46 处（存量） | `tests/test_lint.py::test_all_functions_have_docstrings` | ✅ 已修复 | 为 46 个 public 函数补齐 docstring |
| 集成测试 7 项失败 | `tests/integration/` | ✅ 已修复 | 见下方真实 bug 条目 |
| tech-stack-compliance CI job 用 grep 禁止 langchain/redis/celery，与 pyproject 声明矛盾 | `.github/workflows/ci.yml` + `scripts/check_tech_stack.py` | ✅ 已修复 | 重写为基于 tech-stack.yml 黑名单的合规检查（requirements + import 双扫描），新增单测 |

## 真实 bug（Phase 1 发现并修复，均带回归测试）

| 问题 | 关联测试 | 状态 | 修复记录 |
|------|----------|------|----------|
| Evaluation Layer 9 个 evaluator 并行扇出时返回完整 state，`analysis_result` 等键并发写冲突（InvalidUpdateError） | `tests/integration/test_evaluation_pipeline.py::test_evaluation_initial_state` | ✅ 已修复 | evaluator 只返回 `dimension_scores` 增量，reducer 合并 |
| Planning Layer 自检失败无停止条件，LLM 持续失败时无限递归（Recursion limit） | `tests/integration/test_planning_pipeline.py::test_planning_initial_state` | ✅ 已修复 | 增加 `self_check_attempts` 计数与 `MAX_SELF_CHECK_ATTEMPTS=3` 上限，超限强制组装 |
| `GuardrailResult` 无 `name` 字段，护栏拦截时 gateway 访问 `r.name` 抛 AttributeError | `tests/unit/test_cr_regressions.py::test_guardrail_manager_populates_result_name` | ✅ 已修复 | 数据类补 `name` 字段，GuardrailManager 填充护栏名 |
| `HealthResponse.model_config` 与 Pydantic v2 保留字段冲突，健康接口 model_config 被静默吞掉 | `tests/unit/test_cr_regressions.py::test_health_response_keeps_model_config_field` | ✅ 已修复 | 字段改名 `model_config_status`，validation/serialization alias 保持 API 形状 |
| `KnowledgeGraphBuilder.get_stats()` 与 `SessionCleanupPolicy.cleanup_expired()` 不存在，Celery 任务运行时必崩 | `tests/unit/test_batch.py` + 冒烟 | ✅ 已修复 | 实现 `get_stats()`（Neo4j 实体/关系计数）；清理任务改为按工作空间调用 `policy.cleanup()` |
| `BuildStats` 缺 `relations` 字段，knowledge API 日志访问崩溃 | `tests/unit/test_cr_regressions.py::test_build_stats_has_relations_field` | ✅ 已修复 | 补字段并接入图存储计数 |
| `SessionMessage.attachments` 模型标注为 dict，实际存储 list[dict] | `tests/unit/test_session_history.py` | ✅ 已修复 | 标注改为 `list[dict[str, Any]] | None` |
| `login()` 复用 `result` 变量导致 mypy 行类型推断错乱（TeamMember 被推断为 User） | `mypy` 全量 + `tests/integration/test_auth_flow.py` | ✅ 已修复 | 第二次查询改用独立变量 `member_result` |
| IntegrationHub 测试同步调用 async 方法未 await | `tests/integration/test_integrations.py` | ✅ 已修复 | 测试改为 async + await |

## 未修复 / 待环境确认

| 问题 | 关联测试 / 复现命令 | 状态 | 说明 |
|------|---------------------|------|------|
| E2E 全链路（真实 LLM 调用） | `tests/e2e/test_full_flow.py`（`RUN_E2E_TESTS=1` 时执行） | ⏸ 待 LLM key | 需要 DeepSeek/OpenAI API key 与网络；无 key 时按约定跳过 |
| MinIO 宿主机直连 | `scripts/smoke_test_services.py` | ✅ 已修复（验证容器） | prd2tsd-minio 未发布端口；使用独立 `prd2tsd-minio-verify:9002` 验证通过 |

> 维护约定：修复任何问题必须同步更新本表（状态 + 关联测试），并重跑对应测试。
