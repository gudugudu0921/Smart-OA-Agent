# Smart OA Agent 架构说明

## 模块职责

- `api/routes` 负责 HTTP 参数、认证依赖和错误映射，不拼装复杂业务副作用。
- `services` 负责事务、状态机、通知和审计写入。
- `tools` 是 Agent 到传统 Service 的受控适配层。
- `agents` 负责结构化意图识别、字段补全和 LangGraph 路由。
- `models` 与 `schemas` 分别描述数据库实体和公开 API 数据。
- Vue 端按 API、Pinia store、布局、组件和页面分层。

## JWT 与 RBAC

请求由 `get_current_user` 解码 JWT 并重新查询 active 用户。`require_roles` 执行接口角色限制，Service 再根据 employee、manager、HR 的真实关联和申请状态做最终校验。自然语言里自称角色不会改变 JWT 身份。

## Agent 流程

DeepSeek 通过 `IntentResult` Structured Output 识别意图。LangGraph 根据识别结果路由到查询、提交或审批 Tool；缺少字段时把 `pending_intent` 和 `pending_fields` 保存到 checkpoint，下一轮继续补充。Tool 只调用既有 Service，不直接操作 ORM。

## Redis 职责

Redis 保存 session metadata、用户 session 索引、LangGraph checkpoint、pending intent/fields 和最近查询结果。`thread_id` 与 `user_id` 共同完成会话归属隔离。Redis 不保存请假事实、通知或审计日志。

## MySQL 职责

MySQL 是用户、请假申请、通知和审计的唯一业务事实源。审批待办直接查询当前业务状态，通知是否已读不会改变待办数量。

## 通知设计

`create_notification` 只执行 `db.add`。请假 Service 在业务状态和 audit log 写入后添加 notification，最后由同一次 `commit` 原子提交。通知按 `user_id` 查询和标记已读；不属于当前用户的通知统一表现为 404。

事件映射：

- CREATE_LEAVE → 直属 manager
- MANAGER_APPROVE_LEAVE → employee + 所有 active HR
- MANAGER_REJECT_LEAVE → employee
- HR_APPROVE_LEAVE / HR_REJECT_LEAVE → employee
- CANCEL_LEAVE → 不通知

## 待办设计

系统没有 Celery、定时扫描或消息队列。manager 待办与 `/leave/pending/manager` 使用相同条件；HR 待办与 `/leave/pending/hr` 使用相同条件；employee 与 admin 返回 0。

## 审计设计

审计写入与业务事务一致。Admin API 仅提供带简单过滤的 GET，前端 Detail Dialog 格式化展示 JSON；没有更新、删除或编辑能力。
