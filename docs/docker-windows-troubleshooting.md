# Windows Docker Desktop 启动故障记录

## 本次现象

2026-10-27，Windows 上的 Docker Desktop 4.91.0 在初始化 Ingest 服务时失败：

```text
rename .../Docker/run/sailor-ingest.sock .../sailor-ingest.sock.stale:
The file cannot be accessed by the system.
```

此时 Linux 引擎尚未启动，Docker CLI 找不到 `dockerDesktopLinuxEngine` 管道。
这发生在项目容器启动之前。

## 已验证的恢复方式

1. 正常退出 Docker Desktop；若其已崩溃且无法正常退出，结束确认属于 Docker Desktop 安装目录的残留进程。
2. 从 Windows 开始菜单或资源管理器启动 Docker Desktop。
3. 用 `docker version` 确认同时返回客户端和服务端版本，再检查 `docker compose ps`。
4. 访问项目入口、`/api/health` 和 `/api/ready`。

本次通过 Windows 资源管理器启动后，Docker 服务端恢复，原有四个项目容器健康，
首页返回 HTTP 200，健康接口返回 `ok`，就绪接口返回 `ready`。
恢复过程中未删除、重命名或重置运行目录、WSL 分发、数据盘、镜像或数据卷。

随后执行了一次正常停止，再经 Windows 桌面重新启动；Docker 服务端、原有四个项目容器
和健康接口均再次恢复，没有立即复发。独立空数据库的 Compose 构建和 HTTP 审批验收也通过。

此前直接从代理命令进程启动曾失败；换用桌面启动后成功，说明启动上下文可能影响本次故障。
这不等于已证明底层原因，或保证其他 Windows 环境不会复发。
相同套接字报错也见 [Docker 故障报告](https://github.com/docker/desktop-feedback/issues/676)。

## 仍无法启动时

先保存工作、重启 Windows，再从开始菜单启动 Docker。
不要为了修复启动问题直接恢复出厂设置、注销 Docker WSL 分发或删除数据盘。
进一步处理前按 [Docker 官方备份说明](https://docs.docker.com/desktop/settings-and-maintenance/backup-and-restore/)保护数据，
并按 [排查说明](https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/)收集必要的诊断信息。
分享日志前删除路径、凭据及其他敏感内容。
