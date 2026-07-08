# CODEMAP

把这个文件作为项目查找表。未来 agent 应该能通过它定位功能、模块、文件、符号、测试和当前状态，而不是重新扫描整个仓库。

每个执行任务完成后都要更新这个文件。

## 功能到代码索引

| 区域 | 功能 | 文件 / 模块 | 关键符号 / 接口 | 状态 | 备注 |
|---|---|---|---|---|---|
| 示例 | 用户可见行为 | `src/example.*` | `ExampleService`, `ExampleView` | Not started / Partial / Done | 添加验证或注意事项 |

## 合约索引

| Contract / Type / API | 定义位置 | 消费方 | 变更风险 | 验证 |
|---|---|---|---|---|
| ExampleContract | `src/contracts/example.*` | `src/features/*` | 破坏性变更需要任务规格 | `npm test` |

## 运行时调试地图

| 现象 | 优先检查文件 | Logs / Probes | 已知误区 |
|---|---|---|---|
| 示例 bug | `src/example.*` | `ExampleProbe`, CI test name | 不要在检查 state 前先补 UI |

## 维护规则

- 当任务引入功能、模块、public interface、persistent field、job、probe 或测试面时，新增行。
- 每行保持短小、可操作。超过一段的细节链接到更深文档。
- 明确标记不确定性。过期的 CODEMAP 比稀疏的 CODEMAP 更危险。
