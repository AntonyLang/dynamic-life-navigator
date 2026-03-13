# Step 18–19 审核报告

> 审核时间：2026-03-13  
> 审核范围：Step 18（后端 review 修正）、Step 19（前端 MVP Shell）  
> 基线对比：上一份审核报告 `mvp_backend_review.md`（6 项 gap）

---

## 一、上份审核 Gap 修正情况

| # | 上份 Gap | 修正状态 | 实现质量 |
|---|---------|---------|---------|
| 1 | 🔴 Redis 双层幂等防重 | ✅ 已实现 | `idempotency.py` 使用 `SETNX` + TTL，Redis 失败时优雅降级到 DB |
| 2 | 🔴 `ranking/` 空壳 | ✅ 已实现 | `candidate_ranker.py`（235 行）拆出全部评分逻辑，`__init__.py` 清洁导出 |
| 3 | 🟡 `reset_state` 不使用 CAS | ✅ 已实现 | `state_service.py` 使用 `UPDATE ... WHERE state_version = expected` + 重试 |
| 4 | 🟡 推荐能量 +10 容差未文档化 | ✅ 已文档化 | `candidate_ranker.py` 模块 docstring 显式说明是有意设计 |
| 5 | 🟡 `ingest_webhook_event()` 死代码 | ✅ 已删除 | |
| 6 | 🟡 `request_context.py` 重复 | ✅ 已合并 | `services/request_context.py` 已删除，统一到 `core/` |

> [!TIP]
> **满分修正。** 6 项 gap 全部消解，且每项修正都有配套测试覆盖。

### 新增测试覆盖（34 → 43 passed）

| 新测试文件 | 覆盖内容 |
|-----------|---------|
| `test_webhook_ingestion.py` | Redis 防重成功、Redis 降级到 DB、`occurred_at` ISO/Unix 毫秒解析、fallback 到 ingestion 时间 |
| `test_state_reset.py` | CAS + history 审计、CAS 冲突重试 |
| `test_end_to_end_flow.py` | 完整 ingest→parse→state→recommend 串联（此前缺失的端到端测试）|
| `test_recommendation_flows.py` 扩展 | 能量容差文档化测试 |

---

## 二、Step 18 后端改动详审

### 2.1 Redis 幂等 — `app/core/idempotency.py`

```python
def claim_webhook_idempotency(key, ttl_seconds) -> bool:
    # SETNX + TTL → 已占位返回 False
    # Redis 异常 → 降级 → 返回 True（继续走 DB）
```

**评价：**
- ✅ 符合 Addendum §5 双层幂等要求
- ✅ `RedisError` 异常被捕获并降级，不会因 Redis 不可用阻塞 ingest
- ✅ `lru_cache(maxsize=1)` 避免重复创建 Redis 连接
- ✅ 有配套降级测试 `test_webhook_ingest_degrades_to_db_only_when_redis_unavailable`

> [!NOTE]
> 降级测试使用 `monkeypatch` 模拟 `RedisConnectionError`，覆盖了 Redis 不可用时 webhook 仍然能正常落库的场景。

### 2.2 Webhook `occurred_at` 提取 — `event_ingestion.py`

```python
def _derive_webhook_occurred_at(payload, now):
    for field in ("occurred_at", "event_time", "timestamp", "created_at", "start_time", "updated_at"):
        parsed = _parse_top_level_datetime(payload.get(field))
        if parsed: return parsed
    return now  # 最终 fallback
```

**评价：**
- ✅ 修正了上份审核指出的"使用 ingestion 时间"问题
- ✅ 支持 ISO 8601 字符串（含 `Z` 后缀）和 Unix 毫秒时间戳
- ✅ 字段优先级排序合理（`occurred_at` 最优先）
- ✅ 解析失败时安全 fallback 到 `now`
- ✅ 3 个对应测试完整覆盖

### 2.3 排序重构 — `app/ranking/candidate_ranker.py`

**评价：**
- ✅ 从 `recommendation_service.py`（~330 行评分逻辑）干净拆出到独立模块
- ✅ `get_ranked_candidates()` 为公共 API，同时被 `recommendation_service` 和 `push_service` 复用
- ✅ `CandidateScore` dataclass 使用 `slots=True`，轻量
- ✅ `__init__.py` 提供清洁的 `__all__` 导出
- ✅ `recommendation_service.py` 从 ~338 行瘦身到 125 行，只负责持久化和响应构建
- ✅ `push_service.py` 直接使用 `get_ranked_candidates()` 而非重复评分

### 2.4 状态重置 CAS — `state_service.py`

```python
def reset_state(db, mental_energy, physical_energy, reason, *, max_retries=3):
    for _ in range(max_retries):
        result = db.execute(
            update(UserState)
            .where(UserState.state_version == expected_version)
            .values(state_version=expected_version + 1, ...)
        )
        if result.rowcount == 1:
            # success → write state_history → commit
            return snapshot
        db.rollback()
    raise RuntimeError(...)
```

**评价：**
- ✅ 与 `event_processing.py` 中 `apply_state_patch` 的 CAS 模式完全一致
- ✅ 有 CAS 冲突重试测试（`test_reset_state_retries_on_compare_and_swap_conflict`）

### 2.5 端到端测试 — `test_end_to_end_flow.py`

**评价：**
- ✅ 测试了完整链路：`POST /events/ingest` → `parse_event_log()` → `apply_state_patch()` → `GET /recommendations/next`
- ✅ 验证了状态变更（`focus_mode == "tired"`）和推荐结果正确性
- ✅ 测试清理恢复原始状态，不污染数据库

---

## 三、Step 19 前端 MVP Shell 详审

### 3.1 架构概览

| 层次 | 技术方案 | 评价 |
|------|---------|------|
| 构建 | Vite + React + TypeScript | ✅ 轻量快速，适合 MVP |
| 状态管理 | Zustand（`store.ts`，89 行） | ✅ 简洁，无 boilerplate |
| 服务器状态 | TanStack React Query（`App.tsx`） | ✅ 自动缓存 + 失效 + 乐观更新 |
| API 通信 | 原生 `fetch` + 类型化客户端（`client.ts`，126 行） | ✅ 零依赖，错误映射完整 |
| 样式 | CSS Modules（每组件独立 `.module.css`） | ✅ 无全局冲突 |
| 测试 | Vitest + @testing-library/react | ✅ DOM 级别测试 |

### 3.2 API 合约对齐

| 后端端点 | 前端调用 | 类型定义 |
|---------|---------|---------|
| `GET /api/v1/state` | `apiClient.getState()` | `StateResponse` ✅ |
| `POST /api/v1/chat/messages` | `apiClient.sendChatMessage()` | `ChatMessageRequest/Response` ✅ |
| `GET /api/v1/recommendations/next` | `apiClient.pullRecommendation()` | `RecommendationPullResponse` ✅ |
| `GET /api/v1/brief` | `apiClient.getBrief()` | `RecommendationBriefResponse` ✅ |
| `POST /api/v1/recommendations/{id}/feedback` | `apiClient.submitFeedback()` | `RecommendationFeedbackRequest/Response` ✅ |
| `POST /api/v1/state/reset` | `apiClient.resetState()` | `StateResetRequest/Response` ✅ |
| `POST /api/v1/nodes` | `apiClient.createNode()` | `ActionNodeCreateRequest/Response` ✅ |

> [!TIP]
> 前端 TypeScript 类型与后端 Pydantic schema 完全对齐，字段名保持 snake_case 一致。这使得前后端之间的合约漂移风险最小。

### 3.3 组件结构

| 区域 | 组件 | 功能 | 评价 |
|------|------|------|------|
| Header | `App.tsx` 内联 | 标题 + brief/dev 面板切换 | ✅ 简洁 |
| State Bar | `StateBar.tsx`（51 行） | 实时展示能量/模式/上下文，状态指示 | ✅ 清晰 |
| 聊天区 | `ChatTimeline.tsx`（135 行） | 多类型消息渲染 + 重试 + 推荐反馈 | ✅ 覆盖所有 entry kind |
| 输入框 | `ChatInput.tsx`（80 行） | 命令识别（`/pull`、`/brief`）+ 快捷按钮 | ✅ |
| 推荐侧栏 | `RecommendationSidebar.tsx`（63 行） | 最新推荐展示 + fallback prefill | ✅ |
| Brief | `BriefPanel.tsx`（67 行） | 懒加载 + summary grid + 节点列表 | ✅ |
| Dev 面板 | `DevPanel.tsx`（160 行） | 状态重置 + 节点创建 + 调试事件 | ✅ 表单完整 |

### 3.4 亮点

1. **异步状态协调**：`reconcileState()` 在 chat ack 后轮询 5 次（每次 2s），等待后端异步处理完成后刷新状态。这巧妙地桥接了同步 ack + 异步处理的后端架构。

2. **消息重试不重复**：`submitChatText()` 被 `handleSend` 和 `handleRetryMessage` 共用，重试时复用既有 timeline entry 而非创建新 bubble。

3. **错误映射完善**：API client 区分 409（重复消息）、5xx（服务器错误）、timeout（`AbortError`）、network error，前端展示友好错误文案。

4. **乐观更新**：chat 成功后立即通过 `setQueryData` 更新本地 state 缓存，不等轮询。

5. **Feedback 联动**：dismiss 反馈后自动触发新一轮 `/pull`，对应 PM 中"swap"的产品行为。

6. **Dev 面板实用**：可以直接创建 action node、重置状态、查看原始 JSON 响应和 request/event ID，对联调有价值。

### 3.5 需要关注的问题

#### 🟡 中优先级

| # | 问题 | 影响 | 建议 |
|---|------|------|------|
| 1 | **App.tsx 过大**（521 行） | 所有业务逻辑（7 个 async handler + state 协调 + debug 事件）堆在一个组件中。当前 MVP 可接受，但增长空间有限 | 后续考虑拆分 hooks（如 `useChat`, `useRecommendations`, `useDevActions`）|
| 2 | **`/pull` 和 `/brief` 命令路由重复** | `ChatInput.tsx` 和 `App.tsx` 的 `handleSend` 中都有 `/pull` 和 `/brief` 的命令路由逻辑 | 只在一层做命令分发，另一层直接 passthrough |
| 3 | **Timeline 无虚拟化** | `entries.map()` 渲染所有条目，长时间使用后 DOM 节点会积累 | MVP 可接受，后续考虑 `react-window` 或分页 |
| 4 | **proxy 仅配了 `/api`** | 如果后端有其他路径（如 `/health`）需要在开发时访问，不会被代理 | 确认是否需要额外路径 |

#### 🟢 低优先级 / 建议

| # | 问题 | 建议 |
|---|------|------|
| 5 | `lastDebugEvent` 只保留最近 1 条 | 考虑保留最近 N 条历史，用于联调时回溯 |
| 6 | Chat timeline 是 session-only，刷新即失 | PM 未要求持久化聊天记录，但后续可考虑 localStorage |
| 7 | 无 CORS 配置提示 | 开发时依赖 Vite proxy，文档中应说明生产环境需要后端配置 CORS |
| 8 | `StateBar.tsx` 的 `stale` 状态仅在 query error 时触发 | 可考虑增加"距离上次成功刷新超过 N 秒"的视觉提示 |
| 9 | Feedback 按钮未 disable | 多次快速点击可能触发重复反馈提交 | 建议在 `feedback_submitting` 状态时 disable |

### 3.6 测试覆盖（9 passed，4 files）

| 测试文件 | 测试内容 | 评价 |
|---------|---------|------|
| `client.test.ts` | API 响应解析、409 错误映射、`AbortError` 超时映射 | ✅ 核心错误路径覆盖 |
| `ChatInput.test.tsx` | `/pull`/`/brief` 命令路由、普通文本发送 | ✅ |
| `RecommendationSidebar.test.tsx` | fallback prefill 行为 | ✅ |
| `DevPanel.test.tsx` | 表单 payload 构建 | ✅ |

> [!NOTE]
> 当前前端测试覆盖了输入分发和 API 错误处理的核心路径。缺少 `StateBar` 和 `BriefPanel` 的独立测试，但这两个是纯展示组件，风险较低。缺少 `App.tsx` 的集成测试（如 chat → state update → recommendation 联动），但 MSW 或类似 mock 层需要额外投入，后续可视需要补充。

---

## 四、Vite 配置审查

```typescript
// vite.config.ts
resolve: { preserveSymlinks: true },        // ← 支持 Windows junction 路径
server: { proxy: { "/api": { target: "http://127.0.0.1:8000" } } },
test:   { globals: true, environment: "jsdom", css: true },
```

**评价：**
- ✅ `preserveSymlinks` 解决了 Windows junction 路径与 Vitest 模块解析的冲突
- ✅ API proxy 指向后端默认端口
- ✅ 测试环境配置完整

---

## 五、总体评价

### Step 18 后端修正

> **评分：优秀。** 上份审核的 6 项 gap 全部修正到位，每项修正都有配套测试。Redis 幂等的降级设计、webhook occurred_at 的多格式解析、以及排序模块的干净拆分都体现了工程严谨性。测试数从 34 → 43，增幅 26%。

### Step 19 前端 MVP Shell

> **评分：良好。** 作为一个集成验证 shell，功能覆盖完整（7 个后端端点全部对接），架构选型合理（React Query + Zustand + CSS Modules），代码组织清晰（5 个 feature domain）。最主要的关注点是 `App.tsx` 承载了过多逻辑，以及 `/pull`/`/brief` 命令路由存在重复。但在 MVP 阶段这是可接受的。

---

## 六、下一步建议

| 优先级 | 建议 |
|--------|------|
| 🟡 1 | 从 `App.tsx` 拆分自定义 hooks（`useChat`, `useRecommendations`），减小组件体积 |
| 🟡 2 | 消除命令路由重复（`ChatInput` vs `handleSend`），命令分发只在一层做 |
| 🟡 3 | Feedback 按钮在提交中时 disable，防止重复点击 |
| 🟢 4 | 补充 `App.tsx` 的集成测试（使用 MSW mock 后端） |
| 🟢 5 | 文档中补充 Vite proxy vs 生产 CORS 的说明 |
| 🟢 6 | 启用 Celery worker dispatch（`ENABLE_WORKER_DISPATCH=True`）做一次完整的异步 e2e 验证 |
