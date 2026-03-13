# MVP Backend 审核报告

> 审核时间：2026-03-13  
> 审核范围：全部 PM 文档（`revised_pm/`）、`AGENTS.md`、开发日志（`docs/development-logs/2026-03-13.md`）、全部后端源码  
> 审核依据：V2 PM 主文档 + V2.1 Engineering Addendum 中的工程约束与边界要求

---

## 一、总体评价

**当前 MVP 后端已达到"确定性单用户"阶段的 MVP-complete 基线。**

核心循环完整：事件落库 → 解析 → 状态更新 → 推荐候选筛选 → 排序 → 反馈闭环 → 弱推送评估。代码结构清晰，模型与 PM schema 高度对齐，服务分层合理，测试覆盖（34 passed）涵盖了主要路径。开发日志（17 步）记载了每步所做的决策和修正，质量意识良好。

---

## 二、按 PM 文档逐项对照

### 2.1 数据模型（对照 03_Database_Schema_V2）

| PM 要求 | 实现状态 | 评价 |
|---------|---------|------|
| `user_state` + `state_version` 乐观锁 | ✅ 已实现 | `BigInteger` 版本号 + CAS compare-and-swap |
| `state_history` | ✅ 已实现 | 每次 state 变更都有 before/after 审计记录 |
| `action_nodes` 全部字段 | ✅ 已实现 | 包括 profiling 相关的 `confidence_level`, `profiling_status`, `profiled_at`, `recommended_context_tags` |
| `node_annotations` | ✅ 已实现 | freshness_score, expires_at, fetch_status 对齐 |
| `event_logs` UniqueConstraint | ✅ 已实现 | `(source, external_event_id)` + `(source, payload_hash)` |
| `recommendation_records` | ✅ 已实现 | 包括 ranking_snapshot, rendered_content |
| `recommendation_feedback` | ✅ 已实现 | 反馈枚举完整 |
| 推荐索引 | ✅ 已实现 | GIN 索引 on tags, ai_context, raw_payload |
| `event_logs.ingested_at` + `source_sequence` | ✅ 已实现 | Addendum §6.4 的事件时间字段要求已覆盖 |

> [!TIP]
> 模型层面与 PM 的一致性很好。`ActionNode` 额外增加了 profiling 状态字段，符合 Addendum §2 的冷启动画像要求。`EventLog` 的 `parse_status` 增加了 `'degraded'` 状态，为未来 LLM 结构化输出降级预留了位置。

### 2.2 API 合约（对照 02_API_Workflows_Prompts_V2 + AGENTS.md）

| PM 端点 | 实际实现 | 备注 |
|---------|---------|------|
| `POST /api/v1/chat/messages` | ✅ | ack 式响应含 `accepted`, `processing` |
| `POST /api/v1/webhooks/{source}` | ✅ | 返回 `duplicate` 字段 |
| `GET /api/v1/state` | ✅ | 返回 `UserStateSnapshot` |
| `POST /api/v1/state/reset` | ✅ | 含 `state_history` 审计 |
| `GET /api/v1/recommendations/pull` | ✅ | 含 `limit`, `include_debug` 参数 |
| `GET /api/v1/recommendations/next` | ✅ | 作为 `/pull` 的路由别名 |
| `GET /api/v1/recommendations/brief` | ✅ | 返回 summary + items 结构 |
| `GET /api/v1/brief` | ✅ | 作为 `/recommendations/brief` 的路由别名 |
| `POST /api/v1/recommendations/{id}/feedback` | ✅ | 反馈枚举完整 |
| `POST /api/v1/events/ingest` | ✅ | 复用 chat ingest 路径 |
| `POST /api/v1/nodes` | ✅ | PM 未明确但 Addendum 隐含 |

> [!NOTE]
> AGENTS.md 列出的 5 个最低端点 (`POST /events/ingest`, `GET /state`, `GET /recommendations/next`, `POST /recommendations/{id}/feedback`, `GET /brief`) 全部覆盖。

### 2.3 推荐循环（对照 Addendum §7 + AGENTS.md §6）

| PM 要求 | 实现状态 |
|---------|---------|
| 候选过滤（能量匹配 + 冷却期） | ✅ `_score_node()` 中硬过滤 |
| 排序（priority + urgency + 状态匹配） | ✅ 加权评分 |
| 冷却/抑制（cooldown_hours） | ✅ `_is_on_cooldown()` |
| 最近拒绝惩罚 | ✅ -35 分，3 天窗口 |
| 最近完成惩罚 | ✅ -40 分，1 天窗口 |
| 同类型完成惩罚 | ✅ -20 分，基于 drive_type + tags |
| 曝光疲劳惩罚 | ✅ 最大 -36，递增 12/次 |
| 无候选 fallback | ✅ 返回 `empty_state=true` + `fallback_message` |
| 置信度加分 | ✅ high=+8, medium=+4 |
| DDL 紧迫加分 | ✅ +25，2 天窗口 |
| 新鲜 annotation 加分 | ✅ +10 |
| 反馈持久化 | ✅ `recommendation_records` + `recommendation_feedback` |
| 反馈回写节点信号 | ✅ accepted/rejected/snoozed 分别更新不同字段 |

> [!TIP]
> 推荐排序层是当前实现中最完善的部分。评分分解（`breakdown`）被完整地持久化到 `ranking_snapshot`，为后续调参提供了好的基础。

### 2.4 异步 Worker（对照 05_System_Architecture_V2 + Addendum）

| Worker 任务 | 实现状态 | 备注 |
|------------|---------|------|
| `parse_event_log` | ✅ | 确定性解析 → 成功/回退/失败 |
| `apply_state_patch` | ✅ | CAS 重试 + state_history |
| `profile_new_node` | ✅ | 启发式预填充 → profiling_status |
| `enrich_active_nodes` | ✅ | 内部 annotation 刷新 |
| `compress_event_logs` | ✅ | 保留原始行 → 标记 compressed |
| `recalculate_dynamic_scores` | ✅ | 基于 DDL + 陈旧度 |
| `evaluate_push_opportunities` | ✅ | DND 检查 + 分数门槛 + 重复抑制 |

### 2.5 工程约束（对照 Addendum V2.1）

| 约束 | 实现状态 | 详情 |
|------|---------|------|
| §2 冷启动画像 | ✅ | 默认值对齐（mental=50, physical=20, estimated=30, confidence=low, profiling_status=pending），启发式预填充覆盖 PM 示例 |
| §3 低延迟 ingest | ✅ | 同步 ack + 异步解析/状态更新 |
| §4 LLM 结构化输出 | ⏸️ MVP 可接受 | 当前用确定性规则替代 LLM，符合 MVP 顺序要求 |
| §5 双层幂等防重 | ⚠️ 半完成 | DB 唯一约束 ✅，Redis 短期防重 ❌ |
| §6 状态并发控制 | ✅ | `state_version` CAS + 重试 + state_history |
| §7 推荐观测指标 | ⚠️ 部分覆盖 | 结构化日志有埋点，但无 Prometheus/定期报表 |

---

## 三、亮点

1. **代码分层清晰**：models / schemas / services / workers / api 严格分离，无 god service。
2. **状态审计完备**：每次 state 变更都有 `state_history`，包含 before/after 和 change_reason。
3. **排序可观测**：`ranking_snapshot` 持久化了每个候选节点的评分分解，便于调参。
4. **开发过程透明**：17 步开发日志详细记录了每步的实现决策、review 发现和修正。
5. **防御性编码**：`ingest_chat_message` 捕获 `IntegrityError` 并返回 409，webhook 重复返回 200 + `duplicate: true`。
6. **测试覆盖合理**：34 个测试覆盖了核心路径（config、health、API 合约、事件处理、推荐流、动态评分、推送评估、节点画像、事件压缩）。

---

## 四、需要关注的问题

### 4.1 工程 Gap（按优先级排序）

#### 🔴 高优先级

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | **Redis 双层幂等防重未实现** | Addendum §5 要求用 Redis SETNX 做第一层短期防重。当前只有 DB 唯一约束，webhook 高频重复投递会直接打 DB | 实现 Redis SETNX + 24h TTL 的第一层检查 |
| 2 | **`ranking/` 包是空壳** | `app/ranking/__init__.py` 只有注释，排序逻辑全部写在 `recommendation_service.py` 里 | 将评分逻辑重构到 `ranking/` 包中，保持 service 层轻量 |

#### 🟡 中优先级

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 3 | **`reset_state` 中 `state_version` 递增不使用 CAS** | `state_service.py:60` 直接 `state.state_version += 1`，没有用 compare-and-swap，与 `event_processing.py` 中的 CAS 模式不一致 | 统一使用 CAS 或至少在 reset 路径上也做版本校验 |
| 4 | **推荐能量过滤有 +10 容差** | `recommendation_service.py:124-127` 对能量过滤使用了 `state.mental_energy + 10 < node.mental_energy_required` 的宽松判断，PM 原始 SQL 是严格 `<=` | 确认这是有意的设计决策并文档化，或移除容差 |
| 5 | **`ingest_webhook_event()` 无参版本是死代码** | `event_ingestion.py:109-112` 直接 `raise RuntimeError`，应删除或重定向 | 删除无用函数 |
| 6 | **`request_context.py` 在 `services/` 中有独立副本** | `services/request_context.py` (`get_request_id_from_request`) 与 `core/request_context.py` (`request_id_ctx`) 职责重叠 | 合并到 `core/` |

#### 🟢 低优先级 / 建议

| # | 问题 | 建议 |
|---|------|------|
| 7 | `settings` 在多个 service 文件的模块级初始化 | 可能在测试中造成配置不可覆盖的问题，建议改用依赖注入或函数参数传递 |
| 8 | `_parse_from_event` 只匹配英文关键词 | PM 示例中有中文场景（"刚调完实验"），未来应补充中文 token 匹配 |
| 9 | `push_service` 中 `delivery_status='generated'` 但无实际投递后的状态更新为 `'sent'` | 当前 MVP 未做外部投递是合理的，但需要确保后续真实投递时有状态流转 |
| 10 | Webhook occurred_at 使用 ingestion 时间而非 payload 中的时间 | `event_ingestion.py:137` 对 webhook 的 `occurred_at` 设为 `datetime.now()`，不符合 Addendum §6.4 中基于实际发生时间处理状态的要求 |

### 4.2 测试 Gap

| 类别 | 已有覆盖 | 缺失 |
|------|---------|------|
| 幂等/重复抑制 | ✅ duplicate chat (409), duplicate webhook (200) | ❌ Redis 防重测试 |
| 并发冲突 | ✅ CAS 重试 | ✅ 足够 |
| 推荐排序规则 | ✅ 拒绝惩罚, 完成惩罚, 同类惩罚, 曝光疲劳 | ✅ 足够 |
| 空候选 fallback | ✅ | ✅ |
| 异步画像 | ✅ 基础 profile 回填 | ❌ profile 失败后 `profiling_status='failed'` 的测试 |
| 事件压缩 | ✅ | ✅ |
| Push 评估 | ✅ | ✅ |
| Migration sanity | ✅ `test_db_metadata.py` | ✅ |
| 端到端 API 流程 | ✅ `test_api_contract_shapes.py` | ❌ 完整的 ingest→parse→state→recommend 串联测试 |

---

## 五、与 PM 文档之间仍存在的偏差

| PM 要求 | 当前状态 | 风险等级 |
|---------|---------|---------|
| Webhook Redis 防重 (Addendum §5) | 未实现 | 🟡 中 - 功能正确但有性能风险 |
| LLM 结构化输出 (Addendum §4) | 确定性替代 | 🟢 低 - MVP 明确允许先确定性 |
| 实际 Push 投递 (PM §5.4 步骤 6) | 仅记录决策 | 🟢 低 - MVP 状态文档已声明 |
| Prometheus / 定期报表 (Addendum §7.5) | 仅结构化日志 | 🟢 低 - MVP 最低要求已达标 |
| Webhook `occurred_at` 使用 payload 时间 | 使用 ingestion 时间 | 🟡 中 - 影响状态合成的时序正确性 |
| 事件重建工具 (Addendum §6.7) | 数据结构支持但无工具 | 🟢 低 - PM 明确 MVP 不要求 |

---

## 六、结论与建议

### 当前可交付状态

**后端 MVP 已达到可交付基线**。核心数据循环完整且有审计能力，推荐排序规则覆盖了 PM 要求的全部治理规则，代码质量和测试覆盖在 MVP 阶段属于合理水平。

### 下一步建议（按优先级）

1. **实现 Redis 双层幂等** — 这是当前唯一实质性地偏离 PM 工程约束的 gap
2. **修正 webhook `occurred_at`** — 使用 payload 中的实际发生时间
3. **重构排序逻辑到 `ranking/` 包** — 将 `recommendation_service.py` 的 300+ 行评分逻辑拆分出去
4. **统一 `reset_state` 的并发控制** — 使用与事件处理一致的 CAS 模式
5. **补充端到端串联测试** — ingest → parse → state → recommend 的完整链路
6. **开始前端集成** — 稳定的 API 合约已经就绪
