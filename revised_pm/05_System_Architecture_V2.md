# System Architecture V2

## 1. 架构目标
本架构面向单用户 MVP，但要求未来能平滑扩展到多用户。
关注点包括：
- 低延迟交互
- 可追溯推荐闭环
- 事件驱动与异步富集
- 安全、幂等、可观测

---

## 2. 技术栈建议
- 后端框架：Python + FastAPI
- 数据库：PostgreSQL
- 缓存/队列：Redis
- 异步任务：Celery 或 RQ
- LLM 调用层：官方 SDK + 结构化输出封装
- 可观测：OpenTelemetry + Sentry + Prometheus/Grafana（按实际条件裁剪）

说明：
- MVP 不建议过早引入复杂 Agent 框架。优先使用清晰的 service + task 分层。

---

## 3. 逻辑分层
## 3.1 Interaction Layer
负责接入：
- 桌面插件
- 企业微信/微信
- webhook 来源

职责：
- 鉴权
- 验签
- 参数校验
- request_id 注入
- 基础速率限制

## 3.2 Application Layer
按业务能力拆分 service：
- `event_ingestion_service`
- `state_update_service`
- `recommendation_service`
- `feedback_service`
- `brief_service`

职责：
- 编排业务流程
- 事务边界控制
- 调度 parser / scorer / renderer

## 3.3 Domain / Decision Layer
核心决策模块：
- `state_resolver`
- `candidate_filter`
- `candidate_ranker`
- `push_policy_engine`
- `annotation_selector`

职责：
- 统一推荐规则
- 统一状态变更逻辑
- 避免推荐逻辑散落在 controller / prompt 里

## 3.4 Async Worker Layer
后台任务：
- enrich_active_nodes
- compress_event_logs
- evaluate_push_opportunities
- recalc_dynamic_scores

## 3.5 Data Layer
- PostgreSQL：主存储
- Redis：短期缓存、幂等辅助、任务队列

---

## 4. 同步与异步链路
## 4.1 同步链路：聊天输入
客户端 -> API -> event_ingestion_service -> parser -> state_update_service -> response

要求：
- 主链路尽量在 1~2 次模型调用内完成
- 不把富集、压缩、Push 评估塞进同步请求

## 4.2 异步链路：webhook 与富集
Webhook -> API -> 落 event -> 更新 state -> enqueue push evaluation

定时任务：
- enrich_active_nodes：按活跃节点刷新 annotation
- compress_event_logs：按天压缩日志
- recalc_dynamic_scores：刷新 deadline 紧迫度和长期未触达权重

---

## 5. 推荐引擎内部结构
## 5.1 Candidate Filter
输入：
- user_state
- action_nodes

输出：
- 满足硬约束的候选集合

硬约束：
- active
- energy 符合
- cooldown 未命中
- 未被近期强拒绝

## 5.2 Candidate Ranker
基于以下分量打分：
- state_match_score
- ddl_urgency_score
- long_term_value_score
- freshness_bonus
- repeat_penalty
- rejection_penalty

输出：
- 带可解释分量的候选排序结果

## 5.3 Renderer
只对前 N 个候选调用 LLM 生成自然语言，不让 LLM决定全部业务逻辑。

---

## 6. 安全设计
## 6.1 webhook 安全
- 验签
- 时间戳有效期校验
- 重放防护
- 幂等键校验

## 6.2 凭证管理
- 所有外部 token 使用环境变量或密钥管理服务
- 严禁把第三方 token 写进日志或数据库原始 payload

## 6.3 数据最小化
- 原始 payload 只保留业务必要字段
- 敏感信息脱敏后再存储

---

## 7. 可靠性设计
## 7.1 幂等
- chat message：依赖 `client_message_id`
- webhook：依赖 `external_event_id` 或 `payload_hash`

## 7.2 重试
- 外部 API 抓取失败可重试
- LLM 结构化输出失败最多重试一次
- 发送 Push 失败需记录结果，不无限重试

## 7.3 熔断与降级
- 外部富集失败不影响 Pull 主链路
- LLM 不可用时退回规则模板
- 推荐候选为空时走 fallback

---

## 8. 可观测性
最少需要以下日志/指标：
- API 延迟与错误率
- LLM 调用耗时与失败率
- parser success/fallback/failed 比例
- recommendation 生成数量与空结果比例
- push 发送成功率
- feedback 分布（accepted / rejected / ignored）

建议加统一 trace 字段：
- request_id
- trace_id
- user_id
- event_id
- recommendation_id

---

## 9. 部署建议
MVP 可采用：
- 1 个 API 服务
- 1 个 Worker 服务
- 1 个 PostgreSQL
- 1 个 Redis

不建议在 MVP 一开始拆太多微服务。先保证闭环、规则稳定、日志完整。
