# 发布准备验收记录

日期：2026-10-27。此记录反映本次本地检查，不是生产上线或完整安全审计结论。

| 检查 | 结果 |
| --- | --- |
| 后端完整 unittest 测试集 | 87 项通过，含新增的 10 项流程测试 |
| Python 环境依赖一致性 | `pip check` 通过 |
| 前端锁定依赖安装 | `pnpm install --frozen-lockfile --offline` 通过，使用已有本地缓存 |
| 前端生产构建 | 通过；主 bundle 大于 500 kB 的提示仍存在 |
| Compose 示例配置 | `docker compose --env-file .env.example config --quiet` 通过 |
| 界面截图 | 5 张，真实前端构建 + 虚构接口数据；已逐张查看 |
| 许可证 | MIT |
| GitHub Actions 配置 | 已添加；需推送到 GitHub 后观察实际运行结果 |
| Docker Desktop 与已有项目容器 | 已恢复：Server 29.8.0，四个项目容器健康，首页及健康/就绪接口通过 |
| Docker 正常停止并重新启动 | 通过；重新启动后四个原有容器及健康接口正常 |
| 本地全新 Compose 构建与启动 | 通过；独立项目 `smart-oa-release-check`、空数据卷、18081 端口，四个容器全部健康 |
| 真实 MySQL 与 Nginx HTTP 流程 | 通过：管理员引导、首次改密、旧 Token 失效、角色创建、员工申请、主管审批、HR 终审、审计和通知 |
| GitHub 远程仓库与 Release | 尚未配置、推送或发布 |

## 自动化测试的范围

新增流程测试使用隔离 SQLite 数据库、真实业务 Service、通知及审计持久化，
覆盖员工申请、主管初审、HR 终审、驳回、撤销、日期重叠、重复处理及其他用户访问。
测试专用 DDL 适配 MySQL 的时间默认值和自增整数类型，不修改应用模型。
SQLite 测试不验证 MySQL 的行锁和并发提交行为。

Agent 测试运行真实 LangGraph 编排和参数合并逻辑，使用内存 Checkpoint 和固定结构化模型输出。
因此无需真实模型密钥，也不产生模型调用费用；尚需人工验收外部模型识别质量和 Redis 持久化。

## 发布前仍需观察

Docker 恢复过程见 [Windows 排查记录](docker-windows-troubleshooting.md)。

- 推送仓库后确认 CI 的后端、前端、Compose 三个任务全部通过。
- 首次安装 HTTP 流程已在一次性测试栈通过；正式部署仍应使用自己的配置和账号资料。
- 使用自己的 LLM 配置完成演示脚本；不提交真实配置或凭据。
- 确定仓库 URL 后更新 README 中的 clone 占位地址。

后续修改代码、依赖或部署配置时，应更新相应验证结果。
