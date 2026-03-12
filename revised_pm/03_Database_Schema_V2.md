# Database Schema V2 (PostgreSQL)

本版本目标不是“能存”，而是“能查、能控、能追踪”。
设计原则：
- 核心查询字段结构化
- 语义和扩展信息放 JSONB
- 所有重要动作可追溯
- 为推荐闭环单独留表

## 1. 表清单
MVP 推荐至少包含以下表：
1. `user_state`
2. `action_nodes`
3. `node_annotations`
4. `event_logs`
5. `recommendation_records`
6. `recommendation_feedback`
7. `state_history`（可选但强烈建议）

---

## 2. user_state
保存当前用户状态快照。MVP 可一用户一行，但仍保留可扩展字段。

```sql
CREATE TABLE user_state (
    user_id VARCHAR(64) PRIMARY KEY,
    state_version BIGINT NOT NULL DEFAULT 1,
    mental_energy INT NOT NULL DEFAULT 100 CHECK (mental_energy BETWEEN 0 AND 100),
    physical_energy INT NOT NULL DEFAULT 100 CHECK (physical_energy BETWEEN 0 AND 100),
    focus_mode VARCHAR(32) NOT NULL DEFAULT 'unknown',
    do_not_disturb_until TIMESTAMPTZ NULL,
    recent_context TEXT,
    source_last_event_id UUID NULL,
    source_last_event_at TIMESTAMPTZ NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

说明：
- `state_version` 用于并发更新时的乐观锁
- `source_last_event_id` 便于审计“当前状态最后由谁改写”

---

## 3. state_history
记录状态变化历史，便于回放、调试和调参。

```sql
CREATE TABLE state_history (
    id BIGSERIAL PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    event_id UUID NULL,
    before_state JSONB NOT NULL,
    after_state JSONB NOT NULL,
    change_reason VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_state_history_user_created_at
ON state_history (user_id, created_at DESC);
```

---

## 4. action_nodes
系统候选池的主体。

```sql
CREATE TABLE action_nodes (
    node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL,
    drive_type VARCHAR(20) NOT NULL CHECK (drive_type IN ('project', 'value')),
    status VARCHAR(20) NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'paused', 'archived', 'done')),
    title VARCHAR(200) NOT NULL,
    summary TEXT,
    tags TEXT[] NOT NULL DEFAULT '{}',
    priority_score INT NOT NULL DEFAULT 50 CHECK (priority_score BETWEEN 0 AND 100),
    dynamic_urgency_score INT NOT NULL DEFAULT 0 CHECK (dynamic_urgency_score BETWEEN 0 AND 100),
    mental_energy_required INT NOT NULL DEFAULT 50 CHECK (mental_energy_required BETWEEN 0 AND 100),
    physical_energy_required INT NOT NULL DEFAULT 50 CHECK (physical_energy_required BETWEEN 0 AND 100),
    estimated_minutes INT NULL,
    ddl_timestamp TIMESTAMPTZ NULL,
    cooldown_hours INT NOT NULL DEFAULT 12,
    last_recommended_at TIMESTAMPTZ NULL,
    last_completed_at TIMESTAMPTZ NULL,
    last_rejected_at TIMESTAMPTZ NULL,
    ai_context JSONB NOT NULL DEFAULT '{}'::jsonb,
    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

推荐索引：

```sql
CREATE INDEX idx_action_nodes_user_status
ON action_nodes (user_id, status);

CREATE INDEX idx_action_nodes_user_deadline
ON action_nodes (user_id, ddl_timestamp);

CREATE INDEX idx_action_nodes_user_energy
ON action_nodes (user_id, mental_energy_required, physical_energy_required);

CREATE INDEX idx_action_nodes_tags_gin
ON action_nodes USING GIN (tags);

CREATE INDEX idx_action_nodes_ai_context_gin
ON action_nodes USING GIN (ai_context jsonb_path_ops);
```

---

## 5. node_annotations
把“实时情报”从 action_nodes 主表拆出，便于管理有效期与抓取状态。

```sql
CREATE TABLE node_annotations (
    annotation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL REFERENCES action_nodes(node_id) ON DELETE CASCADE,
    annotation_type VARCHAR(32) NOT NULL,
    content JSONB NOT NULL,
    source VARCHAR(64) NOT NULL,
    freshness_score INT NOT NULL DEFAULT 50 CHECK (freshness_score BETWEEN 0 AND 100),
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMPTZ NULL,
    fetch_status VARCHAR(20) NOT NULL DEFAULT 'success'
        CHECK (fetch_status IN ('success', 'failed', 'expired'))
);

CREATE INDEX idx_node_annotations_node_expires
ON node_annotations (node_id, expires_at DESC);
```

说明：
- 推荐时只读取 `expires_at IS NULL OR expires_at > now()` 的记录
- 避免旧情报长期污染推荐文案

---

## 6. event_logs
保存所有主动/被动事件原始输入与解析结果。

```sql
CREATE TABLE event_logs (
    event_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL,
    source VARCHAR(50) NOT NULL,
    source_event_type VARCHAR(50) NULL,
    external_event_id VARCHAR(128) NULL,
    payload_hash VARCHAR(128) NULL,
    raw_text TEXT NULL,
    raw_payload JSONB NULL,
    parsed_impact JSONB NOT NULL DEFAULT '{}'::jsonb,
    parse_status VARCHAR(20) NOT NULL DEFAULT 'pending'
        CHECK (parse_status IN ('pending', 'success', 'failed', 'fallback')),
    linked_node_ids UUID[] NOT NULL DEFAULT '{}',
    processed_status VARCHAR(20) NOT NULL DEFAULT 'new'
        CHECK (processed_status IN ('new', 'compressed', 'archived', 'deleted')),
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (source, external_event_id),
    UNIQUE (source, payload_hash)
);
```

推荐索引：

```sql
CREATE INDEX idx_event_logs_user_occurred_at
ON event_logs (user_id, occurred_at DESC);

CREATE INDEX idx_event_logs_user_status
ON event_logs (user_id, parse_status, processed_status);

CREATE INDEX idx_event_logs_payload_gin
ON event_logs USING GIN (raw_payload);
```

---

## 7. recommendation_records
记录每次 Pull/Push 结果，是后续优化排序与治理的核心。

```sql
CREATE TABLE recommendation_records (
    recommendation_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(64) NOT NULL,
    mode VARCHAR(20) NOT NULL CHECK (mode IN ('pull', 'push')),
    trigger_type VARCHAR(50) NOT NULL,
    trigger_event_id UUID NULL REFERENCES event_logs(event_id),
    candidate_node_ids UUID[] NOT NULL DEFAULT '{}',
    selected_node_ids UUID[] NOT NULL DEFAULT '{}',
    ranking_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb,
    rendered_content JSONB NOT NULL DEFAULT '{}'::jsonb,
    delivery_status VARCHAR(20) NOT NULL DEFAULT 'generated'
        CHECK (delivery_status IN ('generated', 'sent', 'failed', 'skipped')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_recommendation_records_user_created_at
ON recommendation_records (user_id, created_at DESC);
```

---

## 8. recommendation_feedback
记录用户反馈。

```sql
CREATE TABLE recommendation_feedback (
    id BIGSERIAL PRIMARY KEY,
    recommendation_id UUID NOT NULL REFERENCES recommendation_records(recommendation_id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL,
    node_id UUID NULL,
    feedback VARCHAR(20) NOT NULL
        CHECK (feedback IN ('accepted', 'ignored', 'dismissed', 'rejected', 'snoozed')),
    channel VARCHAR(32) NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_recommendation_feedback_rec
ON recommendation_feedback (recommendation_id, created_at DESC);
```

---

## 9. 关键查询建议
## 9.1 Pull 候选筛选
```sql
SELECT *
FROM action_nodes
WHERE user_id = :user_id
  AND status = 'active'
  AND mental_energy_required <= :mental_energy
  AND physical_energy_required <= :physical_energy
  AND (
    last_recommended_at IS NULL
    OR last_recommended_at < NOW() - (cooldown_hours || ' hours')::interval
  )
ORDER BY dynamic_urgency_score DESC, priority_score DESC
LIMIT 20;
```

## 9.2 新鲜 annotation 读取
```sql
SELECT na.*
FROM node_annotations na
WHERE na.node_id = ANY(:candidate_node_ids)
  AND na.fetch_status = 'success'
  AND (na.expires_at IS NULL OR na.expires_at > NOW());
```

---

## 10. 数据治理建议
- `event_logs` 原始 payload 至少保留 30 天，再决定归档策略
- 含敏感 token 的 payload 必须脱敏后存储
- 压缩 Agent 只能改变 `processed_status`，不能静默删除 recommendation 相关审计数据
- 所有 JSONB 结构建议配套版本字段，如 `schema_version`
