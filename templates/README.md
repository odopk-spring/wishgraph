# Templates / 模板

This directory contains WishGraph source templates. The installer and Skill decide which artifacts a target project actually needs; do not copy this directory wholesale.

本目录保存 WishGraph 的源模板。安装器和 Skill 会按目标项目的实际需要选择产物，请勿整目录复制。

## Target project layout / 目标项目层级

WishGraph may create the following paths:

```text
PRD.md                    # stable product truth, only when needed
ARCHITECTURE.md           # stable architecture truth, only when needed
CODEMAP.md                # sparse code index, only when needed
CONVENTIONS.md            # project-native engineering rules, only when needed
tasks/
  NNN-short-slug.md       # formal Tasks
  revisions/
    NNN-rN.md             # lightweight corrections, created lazily
reports/
  PROJECT_STATUS.md       # the only dynamic project snapshot
  runs/
    <work-unit-id>-attempt-N.md  # actual execution evidence only
```

WishGraph does not create project-level prompt files or a blank Run Report placeholder. Stable role rules stay in the installed Skill and Host Adapter. It also does not restrict user-owned root files such as `AGENTS.md`, `CLAUDE.md`, framework configuration, or native project folders.

WishGraph 不创建项目级 Prompt 文件，也不放置空白 Run Report 占位模板。稳定角色规则保留在已安装的 Skill 与 Host Adapter 中。它也不限制用户自己的根目录文件，例如 `AGENTS.md`、`CLAUDE.md`、框架配置或项目原生目录。

Existing projects should reuse authoritative native documents rather than clone them. Create `tasks/`, `tasks/revisions/`, and `reports/runs/` only when the first corresponding work unit needs them.

已有项目应复用可信的原生文档，不复制第二份事实。`tasks/`、`tasks/revisions/` 和 `reports/runs/` 仅在首次需要对应工作单元时创建。

## Language / 语言

English and language-neutral source templates are at this directory root. Chinese mirrors are under `zh-CN/`. Record a delivery-specific language requirement in the current Task or Project Status; never translate file paths, commands, code symbols, package names, or environment variables.

英文及语言中立模板位于本目录根部，中文镜像位于 `zh-CN/`。与交付有关的语言要求写入当前 Task 或 Project Status；文件路径、命令、代码符号、包名和环境变量不要翻译。
