# ARCHITECTURE

用这个文件描述 agent 必须遵守的依赖边界。

## 系统形态

```text
project/
├── app-or-entrypoints/
├── features/
├── core/
├── services/
├── contracts/
├── tests/
└── docs/
```

用目标项目的真实模块替换这个草图。

## 依赖规则

| 层级 | 可以依赖 | 不允许依赖 |
|---|---|---|
| 入口层 | Features、services、configuration | 内联业务逻辑 |
| Features | Core contracts、services、UI/design system | 存储内部实现、无关 features |
| Core | Contracts、纯模型 | UI、network、filesystem side effects |
| Services | Models、外部 API、storage | feature-specific UI |
| Contracts | 无依赖或纯共享类型 | 具体实现 |

## 所有权边界

| 边界 | 事实源 | 说明 |
|---|---|---|
| 产品行为 | 产品规格 / 任务文件 | 不要把需求只留在执行聊天记录里 |
| Public APIs | Contracts / schema docs | 破坏性变更必须有明确任务 |
| Persistence | Schema / migration docs | 记录兼容性和回滚方式 |
| Validation | Tests / probes / CI | 有风险的变更必须有检查 |

## 架构评审清单

- 改动是否保持依赖方向？
- 是否引入新的 public contract？
- 是否需要 migration 或 rollback notes？
- 是否新增了未来 agent 容易漏看的隐藏状态？
- 验证面是否记录在 `CODEMAP.md`？
