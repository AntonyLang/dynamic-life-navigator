# Core API, Workflows & System Prompts V2

本文档定义 MVP 阶段的接口契约、同步/异步工作流、错误约定与 Prompt 约束。

## 1. API 设计原则
- 所有外部接口统一前缀：`/api/v1`
- 所有写接口返回 request_id，便于链路追踪
- webhook 接口必须支持幂等
- 推荐接口必须落 recommendation_records
- 内部任务优先走 service / task，不强依赖“内部 HTTP 再调自己”

---

## 2. 认证与安全约定
### 2.1 客户端接口
- 聊天入口：Bearer Token 或服务端签名
- 桌面插件：本地配置 API Token
- 企业微信：按官方回调验签

### 2.2 Webhook 接口
- 校验来源签名
- 保存 `external_event_id` 或 payload hash 作为幂等键
- 若重复投递，返回 200 + `duplicate=true`

### 2.3 通用响应头
- `X-Request-Id`
- `X-Trace-Id`

---

## 3. 外部接口契约
## 3.1 POST /api/v1/chat/messages
### 用途
接收用户自然语言输入，落 event_logs，更新 user_state，并可在同一次请求中返回前台回复。

### Request
```json
{
  "channel": "desktop_plugin",
  "message_type": "text",
  "text": "刚调完实验，脑子要烧了",
  "client_message_id": "msg_20260312_001",
  "occurred_at": "2026-03-12T16:20:00+08:00"
}
```

### Response 200
```json
{
  "request_id": "req_xxx",
  "event_id": "evt_xxx",
  "state": {
    "mental_energy": 18,
    "physical_energy": 82,
    "focus_mode": "tired",
    "recent_context": "完成高强度实验调试"
  },
  "assistant_reply": "收到，先记上了。你这一波明显是高脑力消耗。",
  "suggest_next_action": false
}
```

### 失败码
- 400：参数错误
- 401：认证失败
- 409：client_message_id 重复
- 422：解析失败但已落原始事件
- 500：系统错误

---

## 3.2 POST /api/v1/webhooks/{source}
### 用途
接收第三方系统事件，如 Strava / GitHub。

### Path 参数
- `source`: `strava` | `github` | `calendar`

### Request
原始 payload 透传保存；业务层根据 source 解析。

### Response 200
```json
{
  "request_id": "req_xxx",
  "accepted": true,
  "duplicate": false,
  "event_id": "evt_xxx"
}
```

### 要求
- 必须记录原始 JSON payload
- 必须记录 external_event_id / payload_hash
- 重复事件不重复更新状态

---

## 3.3 GET /api/v1/state
### 用途
获取当前用户状态快照，用于前端顶部状态栏刷新。

### Response 200
```json
{
  "request_id": "req_xxx",
  "state": {
    "mental_energy": 18,
    "physical_energy": 82,
    "focus_mode": "tired",
    "do_not_disturb_until": null,
    "recent_context": "完成高强度实验调试",
    "last_updated_at": "2026-03-12T16:20:03+08:00"
  }
}
```

---

## 3.4 POST /api/v1/state/reset
### 用途
手动重置状态，如睡醒、午休后恢复。

### Request
```json
{
  "mental_energy": 70,
  "physical_energy": 75,
  "reason": "午休后恢复"
}
```

---

## 3.5 GET /api/v1/recommendations/pull
### 用途
用户主动请求建议。

### Query 参数
- `limit`：默认 2，最大 3
- `include_debug`：默认 false，仅开发环境可开

### Response 200
```json
{
  "request_id": "req_xxx",
  "recommendation_id": "rec_xxx",
  "mode": "pull",
  "items": [
    {
      "node_id": "node_xxx",
      "title": "沿海骑行 40 分钟",
      "message": "脑子刚烧完就别硬上代码了，天气不错，这会儿更适合去骑一圈。",
      "reason_tags": ["state_match", "fresh_annotation"]
    }
  ],
  "empty_state": false
}
```

### Response 200（无候选时）
```json
{
  "request_id": "req_xxx",
  "recommendation_id": "rec_xxx",
  "mode": "pull",
  "items": [],
  "empty_state": true,
  "fallback_message": "你现在状态有点拧巴，先休息 10 分钟或者告诉我你只想做轻松/短时/不动脑的事。"
}
```

---

## 3.6 GET /api/v1/recommendations/brief
### 用途
返回当前活跃节点简报，供“进度简报”菜单或桌面侧边查看。

### Response 200
```json
{
  "request_id": "req_xxx",
  "summary": {
    "active_projects": 3,
    "active_values": 5,
    "urgent_nodes": 1,
    "stale_nodes": 2
  },
  "items": [
    {
      "node_id": "node_1",
      "title": "期中项目接口完善",
      "status": "active",
      "health": "urgent",
      "next_hint": "距截止 4 天，建议优先补输入接口"
    }
  ]
}
```

---

## 3.7 POST /api/v1/recommendations/{recommendation_id}/feedback
### 用途
接收用户反馈，形成排序学习与 push 治理闭环。

### Request
```json
{
  "feedback": "accepted",
  "node_id": "node_xxx",
  "channel": "wechat"
}
```

### feedback 枚举
- `accepted`
- `ignored`
- `dismissed`
- `rejected`
- `snoozed`

---

## 4. 内部任务接口 / Service 事件
MVP 推荐使用内部 service + queue，而不是 HTTP 调自己。

### 4.1 enrich_active_nodes
- 输入：活跃节点列表
- 输出：更新 live_annotations、expires_at、fetch_status

### 4.2 compress_event_logs
- 输入：时间窗口
- 输出：事件摘要、长期标签变化、日志归档结果

### 4.3 evaluate_push_opportunities
- 输入：状态变化事件 / 定时扫描窗口
- 输出：是否创建 push recommendation

---

## 5. 核心工作流
## 5.1 工作流 A：聊天输入
1. 接收消息
2. 基础鉴权 + client_message_id 幂等校验
3. 落原始事件 event_logs
4. 调用 Data Agent 解析
5. 生成结构化 impact
6. 更新 user_state（带 version 校验）
7. 返回前台回复
8. 如消息本身带 Pull 意图，可继续调用 recommendation service

## 5.2 工作流 B：外部 webhook
1. 验签
2. 提取 external_event_id / payload_hash
3. 检查是否重复
4. 落原始 payload
5. source-specific parser 解析 impact
6. 更新 state
7. 投递 push evaluation 任务

## 5.3 工作流 C：Pull 推荐
1. 读取当前 state
2. 执行 SQL / service 快筛
3. 计算排序分
4. 读取新鲜 annotations
5. 调用 Recommendation Builder 生成最终文案
6. 落 recommendation_records
7. 返回前端

## 5.4 工作流 D：Push 评估
1. 状态突变或定时器触发
2. 检查 push 抑制条件
3. 生成候选并评分
4. 分数未达阈值则放弃
5. 达阈值则生成推送文案
6. 发送消息并记录发送结果

---

## 6. Prompt 设计
## 6.1 Data Agent Prompt
### 目标
把自然语言或 webhook 事件解析成严格结构化的影响。

### System Prompt
> 你是一个后台结构化解析引擎。你的任务不是聊天，而是把输入转换成严格 JSON。
> 
> 规则：
> 1. 只输出 JSON，不要解释。
> 2. `mental_delta` 与 `physical_delta` 取值范围必须在 -100 到 100。
> 3. 若无法确认，保守估计，不要夸张推断。
> 4. 若无法关联具体节点，`linked_node_ids` 输出空数组。
> 5. `confidence` 为 0 到 1 之间的小数。
>
> 输出 schema：
> {
>   "event_summary": "string",
>   "event_type": "chat_update|exercise|coding|study|rest|content_share|other",
>   "mental_delta": -20,
>   "physical_delta": -10,
>   "focus_mode": "focused|tired|bored|recovered|commuting|unknown",
>   "tags": ["#coding"],
>   "linked_node_ids": ["uuid"],
>   "should_offer_pull_hint": false,
>   "confidence": 0.82
> }

### 失败兜底
- JSON 解析失败：重试一次
- 仍失败：保存 raw_input，impact 标记为 `parse_failed`

---

## 6.2 Recommendation Builder Prompt
### 目标
在有限候选内生成简短、自然、可执行的建议。

### System Prompt
> 你是用户的个人导航助手。你只能基于给定状态和候选节点生成建议，不能杜撰新的实时情报。
>
> 规则：
> 1. 只从给定候选里选 1 到 2 个。
> 2. 优先选当前状态下最容易立刻执行的选项。
> 3. 若 annotation 已过期或为空，不要引用。
> 4. 语气自然、简洁、像熟悉用户的朋友，但不要过度表演。
> 5. 如果没有合适候选，输出 fallback，不强行推荐。
>
> 输出 schema：
> {
>   "selected_node_ids": ["uuid"],
>   "items": [
>     {
>       "node_id": "uuid",
>       "message": "string",
>       "reason_tags": ["state_match", "ddl_urgent"]
>     }
>   ],
>   "fallback_message": null
> }

---

## 7. 错误处理与降级
### 7.1 LLM 不可用
- Data Agent：使用规则模板做最小解析
- Recommendation：返回结构化 fallback 建议

### 7.2 无候选节点
- 返回 empty_state
- 引导用户选择轻量条件，如“只看 20 分钟以内”

### 7.3 外部情报失败
- 不阻塞主推荐
- 仅移除 annotation 增益

---

## 8. 审计字段建议
关键日志建议统一包含：
- request_id
- trace_id
- user_id
- event_id / recommendation_id
- parser_version
- prompt_version
- model_name
- latency_ms
