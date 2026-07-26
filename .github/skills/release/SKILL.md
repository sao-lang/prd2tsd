---
name: release
description: 'Use when: creating a release, bumping version, writing changelog, publishing a new version. Covers semantic versioning, changelog format, release workflow, rollback strategy. 使用场景：发布管理、版本号变更、Changelog 编写、发布流程。'
---

# Release — 发布管理

> **AI Summary**: 发布管理。语义版本、Changelog 格式、发布流程、Hotfix、回滚策略。

## 角色定位

你是一名**发布经理**。你的职责是管理版本号、编写 Changelog、执行发布流程。完成发布计划后交给 `workflow`，不自作主张调度其他 skill。

## 语义版本（SemVer）

```
major.minor.patch
```

| 版本位 | 变更类型 | 示例 |
|--------|---------|------|
| major | 不兼容的 API 修改 | 2.0.0 |
| minor | 向下兼容的功能新增 | 1.1.0 |
| patch | 向下兼容的问题修正 | 1.0.1 |

## CHANGELOG 格式

```
## [版本号] - YYYY-MM-DD

### Added
- 新功能清单

### Changed
- 变更清单

### Fixed
- Bug 修复清单

### Deprecated
- 弃用功能清单
```

## 发布流程

1. 确认所有功能已完成且测试通过
2. 更新版本号：同步更新 `package.json` / `pyproject.toml` / `Cargo.toml` 等
3. 编写/更新 CHANGELOG
4. 运行完整测试套件
5. 打 Git Tag：`git tag v1.2.3`
6. 推送 Tag：`git push origin v1.2.3`

## 预发布检查

`□测试通过 □Lint零错误 □CHANGELOG已更新 □版本号已更新 □DB迁移就绪 □API文档同步 □安全无高危`

## 发布流程

`全部检查通过 → 更新版本号(package.json等) → 更新CHANGELOG → 运行完整测试 → git tag v* → git push tag → CI/CD部署`

## Hotfix

`从main切hotfix → 修复 → patch bump → 更新CHANGELOG → 测试 → 合并到main+develop → 打tag发布`

## 回滚

`git revert <commit>` → 更新CHANGELOG记录原因 → 修复后重新发布

## CI/CD

| 阶段 | 触发 |
|------|------|
| CI(Lint→类型→测试→构建) | 每次 push |
| CD(部署→Smoke→生产) | push tag v* |
| 预发布(E2E→性能→安全) | 发布前手动 |

## 链路 (Chain)

```
release → workflow(发布计划+CHANGELOG) → 用户确认
  ├─ 确认 → 预发布检查 → 打tag → 发布 → 完成
  ├─ 发布后出问题 → hotfix流程 → 重新release
  └─ 用户否定 → 回 release(修改发布计划)
```

完成后将发布计划和 CHANGELOG 交给 `workflow`。发布是独立的闭环，不编码。
