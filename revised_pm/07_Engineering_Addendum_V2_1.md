# Engineering Addendum V2.1

本文档是对 V2 主文档的工程补遗，用于补充实现阶段的硬约束与边缘条件处理。

适用场景：使用 Codex + Cursor 进行 MVP 阶段代码生成、实现与联调。

原则上，本文件优先级高于描述性措辞；当 V2 主文档存在实现歧义时，以本文件的工程约束为准。

---

## 1. 目标

V2 已经完成以下主体定义：
- MVP 边界
- 领域模型（state / node / event / recommendation / feedback）
- API 契约
- 数据库主结构
- 前端状态与交互流
- Service + Worker 架构
- 验收用例

V2.1 不改动主体方向，只补充以下高风险工程细节：
1. 新节点冷启动画像
2. 聊天输入链路的低延迟交互
3. LLM 结构化输出强约束
4. Webhook 幂等双层防重
5. user_state 并发写入顺序与重建原则
6. 推荐反馈闭环的观测指标

---

## 2. 新节点冷启动画像机制

### 2.1 背景
`action_nodes` 需要用于过滤与排序的结构化字段，例如：
- `mental_energy_required`
- `physical_energy_required`
- `estimated_duration_minutes`
- `context_tags`

当用户新建节点时，这些字段通常不会被显式输入。如果长期为空，推荐系统会退化为弱过滤。

### 2.2 新增异步任务
新增 Worker：`ProfileNewNodeWorker`

### 2.3 触发条件
当创建新的 `action_node` 且以下任一字段为空或置信度不足时触发：
- `mental_energy_required`
- `physical_energy_required`
- `estimated_duration_minutes`
- `recommended_context_tags`

### 2.4 主链路要求
主链路不得等待 LLM profiling 完成。

创建节点时：
- 先完成落库
- 节点立即可用
- 使用默认值初始化

建议默认值：
- `mental_energy_required = 50`
- `physical_energy_required = 20`
- `estimated_duration_minutes = 30`
- `confidence_level = "low"`
- `profiling_status = "pending"`

### 2.5 启发式预填充
在进入 LLM 异步画像前，允许先使用轻量规则修正默认值，例如：
- tag 含 `exercise` / `ride` / `run`：提高 `physical_energy_required`
- tag 含 `study` / `coding` / `debug`：提高 `mental_energy_required`
- title 含“整理”“收拾”“归档”：降低 mental，提高 physical 或维持中低值
- title 含“复习”“写报告”“调试”：提高 mental

### 2.6 异步画像输入
Worker 可使用以下字段作为输入：
- `title`
- `description`
- `tags`
- `source`
- 最近同类节点的统计画像（若存在）

### 2.7 异步画像输出
Worker 应回填或更新：
- `mental_energy_required`
- `physical_energy_required`
- `estimated_duration_minutes`
- `recommended_context_tags`
- `confidence_level`
- `profiling_status`
- `profiled_at`

### 2.8 失败策略
- profiling 失败不得影响节点存在
- 保留默认值继续服务推荐
- 写入 `profiling_status = "failed"`
- 允许重试
- 重试应设置退避策略，避免持续打模型

---

## 3. 聊天输入链路的低延迟交互要求

### 3.1 背景
如果主链路采用：
`接收消息 -> 调用 LLM 解析 -> 更新状态 -> 返回响应`
则桌面插件、聊天窗口和 IM 场景会出现明显等待。

MVP 必须优先保证输入成功感知，而不是让用户等待完整状态富集结束。

### 3.2 链路拆分原则
聊天输入链路拆成两层：

#### 同步层（Ack Path）
职责：
- 接收输入
- 校验参数
- 落原始事件
- 返回 ack

目标：
- P95 < 500ms
- 即使后续解析失败，也不能影响“输入已收到”的确认

#### 异步层（Processing Path）
职责：
- 调用结构化解析模型
- 写入 `event_logs.parsed_payload`
- 更新 `user_state`
- 触发推荐刷新
- 需要时推送状态变更给前端

### 3.3 前端交互要求
前端必须支持以下临时状态：
- `sending`
- `processing`
- `synced`
- `failed`

建议交互：
1. 用户发送输入后立即进入 `sending`
2. 收到 ack 后切换到 `processing`
3. UI 可展示轻量确认文案，例如：
   - 已记录
   - 正在整理状态
   - 正在消化这条输入
4. 状态更新完成后切换到 `synced`
5. 若解析失败，则显示可恢复提示，但不得丢失原始输入记录

### 3.4 后端接口语义建议
对于 `POST /api/v1/chat/messages`：
- 同步返回只保证“接收成功 + 原始事件已写入”
- 状态快照字段若尚未完成富集，可返回当前快照或 `processing=true`
- 不要求同步等待完整推荐产出

建议响应增加：
```json
{
  "request_id": "req_xxx",
  "event_id": "evt_xxx",
  "accepted": true,
  "processing": true,
  "assistant_reply": "已记录，正在整理状态。"
}
```

### 3.5 实时刷新建议
MVP 可按实现成本选择以下任一方案：
1. 前端短轮询 `GET /api/v1/state`
2. SSE 推送状态更新
3. WebSocket 推送状态更新

若时间有限，优先级建议：
`短轮询 > SSE > WebSocket`

---

## 4. LLM 结构化输出必须使用强约束

### 4.1 背景
禁止仅依赖 Prompt 文本要求模型返回 JSON。

原因：
- 模型可能包裹 markdown fence
- 模型可能附加解释文本
- 多模型切换时，JSON 纯净度不稳定
- 解析失败会直接污染主流程可靠性

### 4.2 允许方案优先级
所有结构化输出链路必须使用以下方案之一，按优先级从高到低：

1. **Structured Outputs / Schema-bound decoding**
2. **JSON Mode**
3. **文本 JSON + 严格 validator + 自动修复重试**

### 4.3 推荐实现
如果使用 OpenAI 兼容接口：
- 优先使用 schema 绑定的结构化输出
- 次选 `response_format = {"type": "json_object"}`

如果使用 Pydantic：
- 为每类模型输出定义独立 Schema
- 在服务层统一执行 runtime validation

### 4.4 必须校验的链路
至少包括：
- 聊天输入状态解析
- 新节点画像
- 推荐理由生成
- 事件压缩 / 总结
- annotation 富集提取

### 4.5 失败处理梯度
建议统一为三级策略：

#### 第一级：自动重试一次
触发条件：
- 非法 JSON
- 缺字段
- 类型错误
- 枚举值非法

#### 第二级：保守降级
若再次失败：
- 写入默认结构
- 设置 `parse_status = "degraded"`
- 继续主流程，不阻塞用户操作

#### 第三级：记录失败
若仍失败：
- 写错误日志
- 落审计记录
- 标记 `parse_status = "failed"`
- 允许后续人工检查或异步补偿任务回放

### 4.6 禁止事项
- 不允许把 markdown fence 清洗当作唯一解析策略
- 不允许因为模型多输出一句解释文字就导致主流程崩溃
- 不允许未校验模型输出即直接入核心表

---

## 5. Webhook 幂等采用双层防重

### 5.1 背景
第三方 webhook 常见重复来源：
- 网络重试
- 对方平台超时重发
- 同一事件多次推送
- 同步补偿任务重复投递

只依赖数据库唯一键虽然正确，但成本较高，且会放大数据库写压力。

### 5.2 方案概览
Webhook 幂等采用双层防重：
- 第一层：Redis 短期防重
- 第二层：数据库唯一约束保底

### 5.3 第一层：Redis 短期幂等
幂等键建议：
`idempotency:{user_id}:{source}:{external_event_id}`

若 `external_event_id` 缺失，可退化为：
`idempotency:{user_id}:{source}:{payload_hash}`

处理逻辑：
- 使用 `SETNX`
- 设置 TTL = 24h
- 命中重复则快速返回幂等成功

作用：
- 拦截短时间重复投递
- 降低数据库唯一索引压力
- 提高 webhook 接入吞吐

### 5.4 第二层：数据库长期保底
在 `event_logs` 或独立幂等表中保留唯一约束，例如：
- `(user_id, source, external_event_id)`
- 或 `(user_id, source, payload_hash)`

作用：
- 提供最终正确性
- 防止 Redis 失效或过期后的重复写入
- 支撑审计与回放

### 5.5 响应语义
对重复 webhook，返回 200，而不是报错。

建议响应：
```json
{
  "accepted": true,
  "duplicate": true,
  "request_id": "req_xxx"
}
```

### 5.6 原则
- Redis 是性能层
- DB 是正确性层
- 两者不可互相替代

---

## 6. 状态写入顺序与并发控制

### 6.1 背景
`user_state` 是快照层，不是事实层。

只保存当前状态虽然利于查询，但如果没有并发控制与事件重建原则，会在高频事件接入时出现：
- 覆盖写
- 乱序写
- 回退状态
- 状态闪烁

### 6.2 数据分层原则
必须明确：
- `event_logs` 是事实层
- `user_state` 是快照层

原则：
- 事实不可丢失
- 快照可重建

### 6.3 乐观锁要求
`user_state` 必须保留 `state_version`

更新时执行 compare-and-swap：
1. 读取当前 state 与 `state_version`
2. 基于 event 计算 patch
3. 仅当版本未变时写入
4. 若版本冲突，则重新读取并重算 patch

### 6.4 事件时间字段
每条事件至少记录：
- `occurred_at`
- `ingested_at`
- `source`
- `source_sequence`（若来源可提供）

### 6.5 乱序处理
当事件乱序到达时：
- 必须允许写入 `event_logs`
- 状态合成需要基于 `occurred_at` 处理，而不是简单按接收顺序覆盖
- 若事件明显过旧，可仅入事实层，不强制重写快照，具体由合成策略决定

### 6.6 状态合成建议
状态合成不建议简单相加减，建议采用 patch 合成：
- 每个事件生成 `state_patch`
- patch 带有置信度与有效期
- 合成器根据事件类型、发生时间和来源优先级做冲突解决

示例：
- “刚骑完车”主要影响 physical 与 context
- “刚写完调试”主要影响 mental 与 focus
- 两者同时存在时不应互相覆盖全部状态字段

### 6.7 重建能力
系统应预留从 `event_logs` 重建 `user_state` 的能力，用于：
- 排查 bug
- 调整状态合成算法
- 灾难恢复
- 离线重算实验

MVP 不一定要实现完整重建工具，但数据结构必须支持。

---

## 7. 推荐反馈闭环的观测指标

### 7.1 背景
有 `recommendation_records` 和 `recommendation_feedback` 还不够，必须进一步定义指标，否则无法稳定调参。

### 7.2 核心指标
建议至少埋以下指标：
- `recommendation_accept_rate`
- `recommendation_dismiss_rate`
- `recommendation_reject_rate`
- `recommendation_snooze_rate`
- `push_open_rate`
- `push_disable_rate`
- `no_candidate_rate`
- `stale_annotation_hit_rate`
- `parse_failure_rate`
- `p95_ingest_latency`
- `p95_recommendation_latency`

### 7.3 行为闭环信号
推荐排序至少要能使用以下反馈信号：
- 用户最近是否拒绝该节点
- 用户最近是否完成同类节点
- 节点最近曝光次数是否过高
- annotation 是否过期
- 当前是否处于免打扰时段
- 当前是否是用户高可执行窗口

### 7.4 最低调参要求
排序逻辑至少支持以下治理规则：
- 最近被拒绝的节点降权
- 最近刚完成的同类节点降权
- 连续曝光未响应的节点降权
- 过期 annotation 不得提供正向加分
- 免打扰窗口内禁止主动 push
- 候选为空时必须输出 fallback，而不是硬推低质量建议

### 7.5 观测实现建议
MVP 可采用：
- 结构化应用日志
- Prometheus 指标
- 周期性 SQL 报表

若时间有限，最低要求是：
- 所有 recommendation 事件都有 request_id
- 所有 feedback 都可追溯到 recommendation_id
- 所有 parse 失败都有明确错误分类

---

## 8. 对 Codex + Cursor 的实施建议

### 8.1 文档使用方式
建议将以下文件同时提供给 Codex / Cursor：
- `01_PRD_V2.md`
- `02_API_Workflows_Prompts_V2.md`
- `03_Database_Schema_V2.md`
- `04_Frontend_Design_V2.md`
- `05_System_Architecture_V2.md`
- `06_User_Scenarios_Validation_V2.md`
- `07_Engineering_Addendum_V2_1.md`

### 8.2 约束优先级
建议在提示中明确：
1. 先遵守数据库和 API 契约
2. 再遵守本文件中的实现约束
3. 最后再自由补充工程细节

### 8.3 代码生成顺序建议
建议按以下顺序生成：
1. 数据库迁移与 ORM 模型
2. Pydantic / Schema 定义
3. Chat ingest API
4. Webhook ingest API
5. user_state service 与 CAS 更新
6. Recommendation service
7. Feedback API
8. Worker：parse / profile / enrich / compress
9. 前端状态同步
10. 测试与 observability

### 8.4 最低测试覆盖建议
至少包括：
- 重复 webhook 幂等测试
- JSON 结构化输出解析失败降级测试
- `state_version` 并发冲突测试
- 新节点默认画像 + 异步回填测试
- 推荐反馈降权生效测试
- 空候选 fallback 测试

---

## 9. 最终原则

V2 负责把系统从“概念设计”推进到“可开发文档”。

V2.1 的目标不是继续扩张功能，而是避免以下几类真实工程事故：
- 用户输入卡顿
- 模型 JSON 输出不稳定导致主链路崩溃
- Webhook 重放污染状态
- 新节点没有画像导致推荐退化
- 状态并发覆盖导致 user_state 不可信
- 有反馈表但没有指标，导致系统无法调优

因此，V2.1 应作为 MVP 实现阶段的工程约束文档与检查清单使用。
