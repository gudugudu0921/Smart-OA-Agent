# GitHub 发布指南

## 仓库范围

只发布 `Smart-OA-Agent` 项目目录。父目录中的备份、pnpm 缓存不属于源码。
不要通过压缩整个工作目录来发布；本地 `.env`、依赖、日志和数据库数据不得上传。

项目采用 [MIT](../LICENSE) 许可。源码和依赖分别遵循其各自许可证，分发时保留所需声明。

## 发布前验证

1. 查看 `git status --short` 和 `git diff`，确认变更范围。
2. 检查 `git ls-files`，确认没有 `.env`、数据库导出、日志或凭据。
3. 后端运行 `python -m unittest discover -s tests -v`。
4. 前端运行 `pnpm install --frozen-lockfile` 和 `pnpm run build`。
5. 在独立测试环境按 README 从空数据库启动 Compose，验证管理员引导、首次改密和审批流程。
6. 按 [演示脚本](demo-guide.md) 验证 Agent 多轮追问和角色切换；真实 LLM 验证需要自己的模型配置。
7. 检查截图只使用虚构数据，不包含凭据、真实邮箱或真实审批内容。

CI 自动运行后端测试、前端构建和 Compose 冒烟检查。Compose CI 使用独立 runner 和一次性数据卷，
不会访问部署者的数据库，也不需要 GitHub Secrets 或真实 LLM Key。
CI 中删除卷的命令只用于该一次性测试栈，不应照搬到已有业务数据的部署中。

CI 还会在全新数据库上运行 `scripts/verify-fresh-install.py`，检查首个管理员引导、首次改密、
旧 Token 失效和通过真实 MySQL/Nginx 的完整审批流程。该脚本会创建虚构数据，
只可在一次性测试栈中使用，且要求 `RELEASE_SMOKE_TEST=1`，数据库已有用户时拒绝引导。

本次已完成的本地验证与尚未完成的环境验证见 [验收记录](release-verification.md)。

## 首次上传

先在 GitHub 创建一个空仓库，避免自动生成 README 与本地历史冲突。
将下列地址换成实际仓库地址，并从项目根目录执行：

```bash
git add LICENSE CHANGELOG.md README.md .github docs backend/tests scripts
git diff --cached --stat
git diff --cached
git commit -m "Prepare project for public release"
git branch --show-current
git remote add origin https://github.com/YOUR_ACCOUNT/Smart-OA-Agent.git
git push -u origin HEAD
```

如果已有 `origin`，先用 `git remote -v` 核对地址，不要重复添加或覆盖其他仓库配置。
上传后在 Actions 页面确认 CI 的三个任务全部通过。
README 的 clone 地址应改为实际地址；发布徽章也应在地址确定后添加。

## 创建首版 Release

确认 CI 和人工演示通过后，将 CHANGELOG 的 `Unreleased` 改为实际版本及发布日期。
前端版本当前为 `0.1.0`，首版标签可使用 `v0.1.0`：

```bash
git tag -a v0.1.0 -m "Smart OA Agent v0.1.0"
git push origin v0.1.0
```

在 GitHub Releases 中选择该标签，将 CHANGELOG 的功能、安装入口和已知限制写入发布说明。
暂未完成验收时可使用 Draft，不要将未验证的功能写为已完成。

## 生成安全的源码压缩包

尚未提交发布补充文件时，可以运行：

```bash
python scripts/package-source.py
```

默认在仓库父目录生成 `Smart-OA-Agent-source.zip`，包含当前已跟踪和未忽略的新文件，
排除已忽略的配置、依赖和构建产物，并拒绝常见敏感文件类型。它会覆盖同名压缩包。
上传前仍应审阅内容；文件名过滤不能代替完整凭据检查。

源码提交完成后，可以从 Git 已跟踪的提交生成压缩包：

```bash
git archive --format=zip --prefix=Smart-OA-Agent/ --output=../Smart-OA-Agent-source.zip HEAD
```

`git archive` 只包含指定提交的文件，不包含未提交改动。
它不会自动检查已跟踪内容是否有秘密，因此仍要先执行发布前检查。
通常直接推送仓库即可，GitHub 会提供对应版本的源码下载。
