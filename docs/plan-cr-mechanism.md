# 实施方案：CR 防回归机制（四道机器闸门 + 基线清单 + 闭环约定）

> **产出日期**：2026-08-15
> **状态**：待确认（按 ai-coding-rules R8，方案确认后进入实施）
> **适用范围**：先以 prd2tsd-agents 为试点落地，再推广到其他项目（通用化设计见第五章）
> **依据**：本方案沉淀自 2026-08-15 关于"为什么每次 CR 都会出现新问题"的讨论，并引用 OpenAI 官方 Codex 文档（AGENTS.md / Skills）作为机制依据

---

## 一、背景与问题定义

### 1.1 现象

- 每次 code review 都会发现之前编码遗留的问题；此前多次让 AI 检查，每次都答复"修改完了"，但问题仍然反复出现。
- 已发现的问题没有沉淀为可核对的记录，下一次 CR 又重新报一遍，修复状态无从追溯。
- 修复本身可能引入新问题（修 A 坏 B），没有回归测试兜底。

### 1.2 根因

| # | 根因 | 后果 |
|---|------|------|
| R1 | 审查依赖模型自觉，无强制机器闸门 | 漏检取决于上下文与抽查，同一问题反复出现 |
| R2 | 无"问题 → 对应测试 → 状态"的可核对基线 | 修没修全靠口头声明，无法机器校验 |
| R3 | 无闭环约定（修复必须带回归测试、必须重跑门禁） | 修复本身成为新问题的来源 |
| R4 | 门禁与现状脱节（存量 lint/type/test 失败长期存在） | 门禁永远红灯，机制形同虚设 |

### 1.3 目标

建立一套机制，使 CR 能做到：

1. **先机器、后人工**：语义审查之前，四道机器闸门必须全绿。
2. **问题可核对**：每个已知问题都有对应测试与状态，机器可校验"是否真的修好"。
3. **修复即闭环**：任何修复必须带回归测试，修完重跑门禁，防止修 A 坏 B。
4. **跨项目可复用**：机制本身通用，项目只提供声明式配置，不重复发明轮子。

---

## 二、机制总览：四道机器闸门 + 一份基线清单 + 一条闭环约定

```
┌─────────────────────────────────────────────────────────────┐
│                     CR 执行流程（机制生效后）                  │
│                                                             │
│  触发 code-review ──► 加载通用 skill 规则                    │
│        │             └─► 读取项目 AGENTS.md（已自动注入）     │
│        ▼                                                    │
│  第一道闸门  静态规范检查（ruff / 对应语言 linter）            │
│  第二道闸门  类型检查（mypy --strict / 对应语言 type check）  │
│  第三道闸门  自动化测试（pytest / 对应语言 test runner）       │
│  第四道闸门  项目预检 cr_preflight                           │
│              ├─ 数据库迁移（alembic）与漂移检查               │
│              ├─ 冒烟测试（真实外部服务连通）                  │
│              ├─ 导入审计（防"import 即崩溃"类断点）           │
│              └─ known-issues 一致性校验                       │
│        │                                                    │
│        ▼                                                    │
│  四道全绿？──否──► 失败项进入本次 CR 待修复清单，禁止跳过     │
│        │是                                                   │
│        ▼                                                    │
│  语义审查（正确性/安全/性能/可维护性/数据流）                 │
│        │                                                    │
│        ▼                                                    │
│  修复要求：每个问题必须带回归测试                             │
│        │                                                    │
│        ▼                                                    │
│  更新 docs/known-issues.md（问题→测试→状态）                 │
│        │                                                    │
│        ▼                                                    │
│  重跑四道闸门 ──全绿──► 提交（本地与 CI 同一套逻辑）          │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 四道机器闸门

| 闸门 | 工具（Python 示例） | 职责 | 失败时 |
|------|--------------------|------|--------|
| 一 | ruff check | 静态规范、未使用导入、格式 | 禁止进入语义审查 |
| 二 | mypy --strict | 类型检查 | 同上 |
| 三 | pytest | 单元 + 集成 + 回归测试 | 同上 |
| 四 | cr_preflight | 迁移/冒烟/漂移/导入审计/known-issues 一致性 | 同上 |

> **说明**：闸门一至三是语言相关工具，通过声明式配置注入（见 5.2）；闸门四是通用 runner，执行配置中的全部 gates 并汇总。

### 2.2 一份可核对的基线清单

- 文件：`docs/known-issues.md`，格式固定为：`问题 | 关联测试 | 状态 | 修复记录`。
- 机器校验：`scripts/check_known_issues.py`，规则：
  - 标记"已修复"的问题，其关联测试必须存在且通过；
  - 标记"未修复"的问题必须仍存在（测试失败或缺失为预期状态）；
  - 任何"已修复但无测试"或"测试失败却标记已修复"的情况直接判失败。

### 2.3 一条闭环约定（写入 AGENTS.md）

1. 审查前必须先执行项目预检，门禁全绿才进入语义审查；
2. 每个确认的问题必须附带回归测试；
3. `docs/known-issues.md` 随修复更新，状态与测试结果一致；
4. 修复完成后重跑全部门禁，全绿才允许提交；
5. 任何"不跑预检就声称已修复"或"删除回归测试"的行为视为违规。

---

## 三、分层实施设计

机制分三层，各自职责单一、互不越界：

| 层 | 载体 | 内容 | 通用性 |
|----|------|------|--------|
| 通用层 | code-review skill（独立技能仓库） | 审查前置的通用条款：若项目声明了预检，必须先执行 | 所有引用该 skill 的项目共享，改一处全部生效 |
| 项目层 | 各项目 `AGENTS.md` | 项目事实 + 具体预检命令 | 每个项目一份，模板生成 |
| 执行层 | 通用工具 + 项目配置 + CI workflow | 配置驱动的 gate runner、known-issues 校验、CI 模板 | 工具与模板通用，配置项目化 |

### 3.1 通用层：code-review skill 修改（不写具体脚本名）

在独立技能仓库 `code-review/SKILL.md` 中新增通用条款（草案）：

```markdown
## 审查前置（通用条款）

- 若项目通过 AGENTS.md / README / 项目配置（如 cr-config.*）声明了审查前置检查（preflight），
  必须先完整执行并确认全部通过，再进入语义审查。
- 前置检查失败时，失败项必须列入本次审查的待修复清单，禁止跳过、忽略或以"已知问题"名义放行。
- 修复后必须重新执行前置检查，并核对已知问题清单（known-issues）是否同步更新、状态是否与测试结果一致。
```

> **为什么 skill 不写具体脚本名**：skill 是通用能力，被多个项目共享；具体命令属于项目事实，由 AGENTS.md/配置声明。skill 只负责"发现并执行项目声明的预检"。

### 3.2 项目层：AGENTS.md（prd2tsd 试点草案）

```markdown
# AGENTS.md

## 项目事实

- 语言/框架：Python 3.12+ / FastAPI / LangGraph / SQLAlchemy / Alembic
- 外部依赖：PostgreSQL(pgvector)、Redis、MinIO、Neo4j、Jaeger、Prometheus（docker-compose 已定义）
- 预检配置：.codex/cr-config.yaml（闸门命令的唯一事实源）

## Code Review Rules

- 审查前必须运行 `python -m cr_toolkit.preflight --fast`，四道闸门全绿后才进入语义审查。
- 闸门定义见 `.codex/cr-config.yaml`；不得绕过、跳过或忽略任一 gate。
- 每个确认的问题必须附带回归测试，修复后更新 `docs/known-issues.md` 并重跑预检。
- 禁止：不跑预检直接声称"已修复"；删除回归测试；标记"已修复"但测试未通过。
```

> **注意**：AGENTS.md 有 32 KiB 合并上限（见第七章），模板必须精简，只写项目事实与规则，不堆砌细节。

### 3.3 执行层：脚本与配置清单

#### 通用工具（放独立仓库，供所有项目复用）

| 文件 | 职责 |
|------|------|
| `cr_toolkit/preflight.py` | 配置驱动的 gate runner，支持 `--fast` / `--ci` 两档 |
| `cr_toolkit/check_known_issues.py` | 解析 `known-issues.md` 并机器校验状态与测试 |
| `cr_toolkit/init.py` | `cr init` 脚手架：生成项目配置 + AGENTS.md + CI workflow 模板 |
| `templates/AGENTS.md.template` | AGENTS.md 生成模板 |
| `templates/cr-config.example.yaml` | 声明式配置示例（含 Python/TS/Go 等语言 gate 模板） |
| `templates/ci.yml.template` | GitHub Actions workflow 模板 |

#### 项目配置文件（每个项目一份，声明式）

```yaml
# .codex/cr-config.yaml
version: 1
gates:
  - id: lint
    label: 静态规范
    cmd: "ruff check app/ tests/ contracts/"
  - id: type
    label: 类型检查
    cmd: "mypy app/ contracts/ --strict --ignore-missing-imports"
  - id: test
    label: 自动化测试
    cmd: "pytest tests/ -q"
preflight:
  cmd: "python scripts/cr_preflight.py"
known_issues: "docs/known-issues.md"
```

> **要点**：gate 命令是任意 shell 命令，返回码即通过/失败；因此同一套 runner 可以驱动任何语言项目（TS 写 `eslint/tsc/test`，Go 写 `go vet/go test`）。

#### prd2tsd 项目内新增脚本（试点期由通用工具逐步替换）

| 脚本 | 职责 |
|------|------|
| `scripts/cr_preflight.py` | 预检入口：alembic 迁移 → 冒烟 → 漂移 → 导入审计 → known-issues 校验 |
| `scripts/audit_imports.py` | 全量导入审计，防"import 即崩溃"类断点 |
| `scripts/drift_check.py` | alembic 迁移与模型元数据一致性检查 |
| `scripts/check_known_issues.py` | known-issues 机器校验（过渡期先放项目内，随后上收通用工具） |

### 3.4 CI 层：GitHub Actions 改造

- `lint-and-type-check` job：保留 ruff + mypy（闸门一、二）。
- `test` job：补充 redis service；integration 测试前先跑 `alembic upgrade head`。
- 新增 `preflight` job：起 postgres/redis service → `python -m cr_toolkit.preflight --ci`（含迁移、冒烟、漂移、导入审计、known-issues 校验）。
- **删除或重写过时的 `tech-stack-compliance` job**：当前它用 grep 禁止 `langchain/redis/celery`，但 `pyproject.toml` 明确依赖这些包——门禁与现状矛盾，属于典型的"门禁永远红灯"来源，必须先修。
- 本地与 CI 调用同一套逻辑（同一 runner、同一配置），保证"本地绿 = CI 绿"。

---

## 四、存量清剿（试点前置条件，必须先清零）

门禁机制的前提是"门禁能全绿"。以下存量问题不清零，机制落地即失败：

| # | 存量问题 | 现状（最近一次扫描） | 处理 |
|---|---------|---------------------|------|
| 1 | ruff 违规 | 37 条 | 全部清零 |
| 2 | mypy 违规 | 约 200 条（type-arg 72 / attr-defined 42 / no-any-return 23 为主） | 全部清零，或对合理位置显式排除并记录到 known-issues |
| 3 | test_batch 失败 | 依赖 Redis broker | 借 Redis service / mock 修复 |
| 4 | tech-stack CI job 过时 | grep 禁止的依赖正是 pyproject 声明的依赖 | 删除或重写为基于 pyproject 的合规检查 |
| 5 | test_ingestion tmp_path 权限问题 | 环境相关失败 | 修复或明确排除并记录 |

---

## 五、通用化设计（跨项目复用）

### 5.1 通用化目标

其他项目同样存在"每次 CR 都有遗留问题"，机制必须开箱即用，而不是每个项目重新写一遍：

1. 机制代码（runner、校验、模板）只有一份，跨项目共享；
2. 项目只需要一份声明式配置 + 生成出的 AGENTS.md/CI；
3. 语言无关：Python/TS/Go/Rust 等通过配置注入各自的 gate 命令；
4. skill 层改一处，所有项目受益。

### 5.2 抽象层次

```
┌─ 通用层（一份，跨项目共享）───────────────────────────────┐
│  code-review skill（通用条款）                            │
│  cr_toolkit（runner + 校验 + init 脚手架）                 │
│  模板（AGENTS.md / cr-config / ci.yml）                   │
└──────────────────────────────────────────────────────────┘
                            │ 引用
                            ▼
┌─ 项目层（每项目一份，声明式）──────────────────────────────┐
│  .codex/cr-config.yaml   ← gate 命令唯一事实源             │
│  AGENTS.md               ← 项目事实 + 预检要求             │
│  docs/known-issues.md    ← 基线清单（格式通用）            │
│  .github/workflows/ci.yml ← 模板生成，可覆盖               │
└──────────────────────────────────────────────────────────┘
```

### 5.3 落地形态（推荐：工具仓库 + 技能仓库分离）

| 仓库 | 内容 | 职责 |
|------|------|------|
| 技能仓库（现有 `E:\vsc-workspace\lania-zip\skills`） | code-review 等 skill | 通用行为规则（模型侧） |
| 工具仓库（新建，如 `cr-toolkit`） | runner / 校验 / init / 模板 | 机器保障（脚本侧） |
| 各项目仓库 | 配置 + 生成的 AGENTS.md/CI | 项目事实 |

- 项目通过 `.agents/skills` 引用技能仓库（解决未提交问题后，改用 submodule 或安装机制固化）。
- 项目通过 `pip install` 或 vendored 方式引入 `cr-toolkit`（依赖 Python 3.12+；对非 Python 项目可用独立 venv 或容器执行 runner）。

### 5.4 跨语言模板示例

```yaml
# cr-config.example.yaml 中的语言 gate 模板
python:
  lint: "ruff check ."
  type: "mypy . --strict --ignore-missing-imports"
  test: "pytest tests/ -q"
typescript:
  lint: "eslint . --max-warnings=0"
  type: "tsc --noEmit"
  test: "npm test -- --runInBand"
go:
  lint: "go vet ./..."
  type: "go build ./..."
  test: "go test ./..."
```

### 5.5 通用化的边界与风险

| 风险 | 说明 | 对策 |
|------|------|------|
| gate 命令即 shell 命令 | 配置不可信时执行有风险 | 只在受信任的项目配置下运行（本地/CI），禁止解析不可信输入 |
| 非 Python 项目依赖 runner | runner 需要 Python 3.12+ | 用独立 venv 或容器执行；或提供语言原生版本（后续按需） |
| 模板生成后漂移 | 项目改了模板，工具升级不回去 | `cr init` 生成时记录版本；`cr check` 检测配置/模板版本 |
| 多项目维护成本 | 各项目门禁配置不一致 | 配置 schema 版本化 + 示例模板统一维护 |

---

## 六、实施阶段与验收标准

### Phase 0：基线采集（试点：prd2tsd-agents）

- 跑全部四道闸门，记录失败项，生成 `docs/known-issues.md` 初版。
- 验收：known-issues 覆盖所有已知失败项，每条关联一个测试或复现命令。

### Phase 1：存量清剿

- ruff 37 条、mypy 约 200 条、test_batch、tech-stack CI job 全部清零。
- 验收：本地 `ruff && mypy && pytest` 全绿；`known-issues.md` 中对应项标记"已修复"且测试通过。

### Phase 2：通用工具开发（cr_toolkit）

- 实现配置驱动 runner、known-issues 校验、init 脚手架、模板。
- 验收：`cr_toolkit` 自带测试；用示例配置在临时项目上跑通全流程。

### Phase 3：试点项目接入

- prd2tsd 生成 `.codex/cr-config.yaml`、`AGENTS.md`、改造 CI。
- 改独立技能仓库 code-review skill，加通用前置条款。
- 验收：模拟一次 CR，确认"预检失败 → 修复 → 回归测试 → 预检通过"全流程走通；用官方验证命令确认 AGENTS.md 与 skill 同时加载。

### Phase 4：跨项目推广

- 选一个非 Python 项目做第二试点，验证语言无关性。
- 验收：第二项目用模板生成配置后，机制原样生效。

### Phase 5：机制固化

- 处理 `.agents/skills` 软链接未提交问题（submodule 或安装机制）。
- 处理 `.github/skills` 副本漂移（若存在）。
- 验收：新机器 clone 后一条命令初始化即可用。

---

## 七、机制依据：skills 与 AGENTS.md 如何同时工作

### 7.1 两条独立注入通道

| 通道 | 加载方式 | 内容 | 证据 |
|------|---------|------|------|
| AGENTS.md | 每次 run 开始自动读取（无需触发词） | 项目规则与命令 | 官方 [AGENTS.md 文档](https://learn.chatgpt.com/docs/agent-configuration/agents-md.md) |
| Skills | 渐进式披露，命中后完整读取 SKILL.md | 通用能力规则 | 官方 [Skills 文档](https://developers.openai.com/codex/skills.md) |

关键事实：

- AGENTS.md 加载顺序：全局 `~/.codex/AGENTS.md` → 项目根向下到 cwd，离 cwd 越近覆盖越早；合并上限默认 32 KiB。
- 官方明确支持 `## Code Review Rules` 段落，同一个 AGENTS.md 可同时指导编码与审查。
- 官方提供验证方法：`codex --ask-for-approval never "List the instruction sources you loaded"`。
- 本会话实证：可用技能列表已包含 code-review / ai-coding-rules / git 等（经 `.agents/skills` 软链接加载），说明 skill 通道在工作；AGENTS.md 通道待落地后验证。

### 7.2 分工

- skill 负责通用规则："若项目声明了预检，必须先执行"——不写具体命令。
- AGENTS.md 负责项目事实："本项目的预检是 `python -m cr_toolkit.preflight --fast`"。
- 两者叠加进入同一份上下文，Codex 自然把规则与命令串起来执行。

---

## 八、风险与待决事项

| # | 事项 | 现状 | 待决 |
|---|------|------|------|
| 1 | `.agents/skills` 软链接未提交 | 新机器/CI 不保证存在 | 拍板：git submodule / 安装机制 / 维持手工 |
| 2 | skill 副本漂移 | 独立技能仓库为权威 | 确认项目内是否有 `.github/skills` 副本，有则同步或删除 |
| 3 | 未提交删除文件 | `DEVELOPMENT_GUIDE.md`、`VIBE_CODING_RULES.md` 已被删 | 确认是否保留/归档 |
| 4 | 端口冲突 | 另一项目 `im` 栈占用 5432/6379/9000；验证用 Postgres 在 5433 | 确认统一端口分配策略 |
| 5 | 通用工具仓库归属 | 尚未创建 | 确认仓库名/位置/授权方式 |
| 6 | 非 Python 项目的 runner 依赖 | runner 需 Python 3.12+ | 确认独立 venv/容器方案 |

---

## 九、对话决策记录

| 时间 | 决策/纠正 | 影响 |
|------|----------|------|
| 2026-08-15 | 用户："项目外设在 docker 中都已有了，直接启动对应容器" | 验证环境用真实容器，不再 mock |
| 2026-08-15 | 用户纠正："code-review 会执行对应 skill；skill 是通用的，不适合把项目脚本执行写进 skill" | 分层设计：skill 只写通用条款，项目脚本由 AGENTS.md/配置声明 |
| 2026-08-15 | 用户确认分层方案（AGENTS.md 项目层 + skill 通用层 + CI 层） | 本方案第三、五章 |
| 2026-08-15 | 用户："这套方案能不能也做成通用的？其他项目也有这个问题" | 本方案第五章通用化设计 |
| 2026-08-15 | 已推送 18 项断点修复 + 2 个真实 bug 修复（master = e12e696） | 作为机制试点的基础存量 |

---

> **本文档状态**：待用户确认后进入 Phase 0-1 实施。
