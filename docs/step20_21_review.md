# Step 20–21 审核报告

> 审核时间：2026-03-13  
> 审核范围：Step 20（前端 shell hardening）+ Step 21（前后端集成启动 + 清理）  
> 基线对比：上一份审核报告 `step18_19_review.md`（4 项中优先级 + 5 项低优先级）

---

## 一、上份审核 Gap 修正情况

| # | 上份 Gap | 优先级 | 修正状态 | 实现质量 |
|---|---------|--------|---------|---------|
| 1 | `App.tsx` 过大（521 行），应拆分 hooks | 🟡 中 | ✅ 已修正 | 521→208 行，拆出 4 个 hooks + `flowUtils` |
| 2 | `/pull`/`/brief` 命令路由在 `ChatInput` 和 `handleSend` 中重复 | 🟡 中 | ✅ 已修正 | `ChatInput` 不再分支，命令路由统一在 `App.handleInputSubmit()` |
| 3 | Feedback 按钮缺少 disable 状态 | 🟡 中 | ✅ 已修正 | `feedback_submitting` 状态下按钮禁用 |
| 4 | 补充 `App.tsx` 集成测试 | 🟡 中 | ✅ 已修正 | 5 个 App 级集成测试（chat→ack→state、/pull 路由、dismiss→repull、retry 不重复 bubble、dev 面板 reset→recommendation） |
| 5 | `StateBar` 仅在 query error 时 stale | 🟢 低 | ✅ 已修正 | `lastSuccessfulAt` + 60s 阈值双条件判定 |
| 6 | `lastDebugEvent` 只保留 1 条 | 🟢 低 | ✅ 已修正 | 扩展到最近 5 条，newest-first |
| 7 | CORS / proxy 生产说明 | 🟢 低 | ⬜ 暂未处理 | 后续可在 README 或部署文档中补充 |

> [!TIP]
> **4/4 中优先级项目全部修正，2/5 低优先级也已修正。** 仅 CORS 说明和 Timeline 虚拟化（合理推迟到有真实用量时）未做。

---

## 二、Step 20 前端 Hardening 详审

### 2.1 Hook 提取架构

| Hook | 行数 | 职责 | 评价 |
|------|------|------|------|
| [useChatFlow](file:///e:/Antony/Documents/individual-assistant/frontend/src/app/hooks/useChatFlow.ts) | 142 | chat mutation + reconcileState polling + retry | ✅ 完整封装 send/retry/isPending |
| [useRecommendationFlow](file:///e:/Antony/Documents/individual-assistant/frontend/src/app/hooks/useRecommendationFlow.ts) | 162 | pull mutation + feedback mutation + timeline 状态管理 | ✅ 3 种失败状态清晰分离 |
| [useDevActions](file:///e:/Antony/Documents/individual-assistant/frontend/src/app/hooks/useDevActions.ts) | 80 | state reset + node create + silent recommendation refresh | ✅ 轻量 |
| [useDebugEvents](file:///e:/Antony/Documents/individual-assistant/frontend/src/app/hooks/useDebugEvents.ts) | 27 | debug 事件写入 store | ✅ 薄包装 |
| [flowUtils](file:///e:/Antony/Documents/individual-assistant/frontend/src/app/hooks/flowUtils.ts) | 44 | `makeId`, `reconcileState`, `toErrorMessage`, `STATE_STALE_THRESHOLD_MS` | ✅ 公共工具 |

**亮点：**
- 每个 hook 返回 `isPending` flag，`App.tsx` 用这些 flag 控制 UI disable 状态
- `reconcileState` 保持了 5 次 × 2s 的轮询策略，被 `useChatFlow` 调用，不再内联
- `useDevActions` 通过 `refreshRecommendationsSilently` callback 注入推荐刷新，避免了 hook 之间直接耦合

### 2.2 命令路由统一

**Before (Step 19):**
```
ChatInput ──(if /pull)──> onPull()       ← 分支 1
            ──(if /brief)──> onBrief()    ← 分支 2
App.handleSend ──(if /pull)──> handlePull() ← 分支 3 (重复)
```

**After (Step 20):**
```
ChatInput ──(always)──> onSend(rawText)
App.handleInputSubmit ──(if /pull)──> handlePull()
                      ──(if /brief)──> handleBrief()
                      ──(else)──> sendChatMessage()
```

✅ 命令分发现在只在 `App.tsx` 一处发生。`ChatInput` 变成纯粹的文本提交组件。

### 2.3 推荐 Timeline 状态语义

Step 19 的 `status` 只区分 `loading`/`ready`/`empty`。Step 20 新增了 3 个状态：

| 新状态 | 含义 | 触发场景 |
|--------|------|---------|
| `load_failed` | 拉取推荐失败 | `handlePull` catch |
| `feedback_submitting` | 反馈正在提交 | 按下 Accept/Snooze/Swap 时 |
| `feedback_failed` | 反馈提交失败 | `handleRecommendationFeedback` catch |

✅ 这解决了之前"加载失败和反馈失败混用同一状态"的问题。

### 2.4 StateBar 增强

```tsx
const staleByAge = lastSuccessfulAt !== null && now - lastSuccessfulAt > STATE_STALE_THRESHOLD_MS;
const isStale = stale || staleByAge;
```

- ✅ 每 15 秒刷新 `now`，不引起不必要的 re-render
- ✅ 两条 stale 路径有分别的提示文案（error vs age）
- ✅ `STATE_STALE_THRESHOLD_MS` 从 `flowUtils` 导出，值 60s

### 2.5 集成测试 (`App.test.tsx`)

| # | 测试名称 | 覆盖场景 | 评价 |
|---|---------|---------|------|
| 1 | chat → ack → state refresh | 主链路：输入 → 发送 → assistant 回复 → state 更新 → status `synced` | ✅ |
| 2 | /pull only through app dispatcher | 验证 `/pull` 不触发 `sendChatMessage` | ✅ |
| 3 | dismissed feedback → repull | 验证交互链路：pull → dismiss → auto-repull with limit=1 | ✅ |
| 4 | retry without duplicate bubble | 发送失败 → 重试 → 成功，全程只有 1 个 user bubble | ✅ 关键回归测试 |
| 5 | dev-panel reset → silent recommendation refresh | 重置后自动拉取推荐 | ✅ |

**测试基础设施亮点：**
- `renderWithProviders` 创建隔离的 `QueryClient`（`retry: false`），避免异步重试干扰
- `useAppStore.getState().resetForTests()` 在 `beforeEach` 中重置 Zustand store
- mock 使用 `vi.mocked()` + `mockResolvedValue` / `mockRejectedValue` 链式配置
- `waitFor` + `findByText` 等待异步更新

### 2.6 测试增量

| 指标 | Step 19 | Step 20 | 增量 |
|------|---------|---------|------|
| 前端测试文件 | 4 | 8 | +4 |
| 前端测试数 | 9 | 20 | +11 |

新增测试文件：`App.test.tsx`（5 tests）、`store.test.ts`（1 test）、扩展到现有文件。

---

## 三、Step 21 集成启动详审

### 3.1 本地后台管道 — `local_pipeline.py`

```python
def run_local_event_pipeline(event_id: str):
    with SessionLocal() as session:
        parse_event_log(session, event_id)
    with SessionLocal() as session:
        apply_state_patch_from_event(session, event_id)
    with SessionLocal() as session:
        evaluate_push_opportunities(session, event_id)
```

**评价：**
- ✅ 解决了无 Celery 时前端轮询永远看不到状态变更的核心问题
- ✅ 每步使用独立 session，避免跨步骤 session 污染
- ✅ 异常被捕获并记录，不会阻塞其他请求
- ✅ 仅在 `enable_worker_dispatch=False` 且有 `BackgroundTasks` 时启用

> [!IMPORTANT]
> 这个改动修正了一个真正的集成阻塞：在 worker-off 本地开发中，chat ingest 后前端 reconcile 轮询会永远收到旧状态。解决方案保持了 PM 的关键约束——同步 ingest 仍然只返回 ack，重活仍然异步执行。

### 3.2 `_enqueue_parse_task` 改动

```python
def _enqueue_parse_task(event_id, background_tasks=None):
    if not settings.enable_worker_dispatch:
        if background_tasks is not None:
            background_tasks.add_task(run_local_event_pipeline, event_id)
            return
        return   # ← 老行为：什么都不做
    parse_event_log.delay(event_id)  # ← Celery 路径
```

- ✅ `BackgroundTasks` 注入通过 `routes_events.py` 和 `routes_webhooks.py`
- ✅ 当 `background_tasks` 为 `None`（如直接调用服务层函数）时 graceful 降级

### 3.3 测试清理加固

| 改进 | 之前 | 之后 |
|------|------|------|
| webhook 测试 | 只清理 `event_log` | 清理 `recommendation_records`(push) + `state_history` + `event_log` + 恢复 `user_state` |
| contract 测试 | 只清理 `event_log` | 同上 |
| 清理函数 | 内联在每个测试中 | 提取为 `_snapshot_user_state` / `_restore_user_state` / `_cleanup_webhook_artifacts` |

- ✅ 解决了全量测试跑完后 `user_state` 被污染的问题
- ✅ 每个测试的 `finally` 块使用统一的恢复函数

> [!NOTE]
> `_snapshot_user_state` / `_restore_user_state` 在 `test_webhook_ingestion.py` 和 `test_api_contract_shapes.py` 中存在重复。建议后续提取到 `tests/conftest.py` 的 `@pytest.fixture`。

### 3.4 集成检查清单 (`frontend-backend-integration-checklist.md`)

| Phase | 覆盖范围 | 通过状态 |
|-------|---------|---------|
| **A: 运行时基线** | `/health` + `/state` 可达 + dev panel 可见性 | ✅ API 通过，浏览器侧待确认 |
| **B: 五条金色链路** | chat→state、pull→display、brief、feedback→repull、dev panel | ✅ API 全通过，proxy 全通过 |
| **C: 异步一致性** | worker-off 本地管道、stale/error 语义 | ✅ 自动化覆盖 + proxy 烟雾通过 |

**评价：**
- ✅ 检查清单结构清晰、可审计
- ✅ 每个流程都有 UI / API / DB 三层验证标准
- ✅ 实际 HTTP 烟雾测试在两个路径上完成（直接 uvicorn + Vite proxy）

### 3.5 集成问题追踪 (`frontend-backend-integration-issues.md`)

| 类别 | Open | Resolved |
|------|------|----------|
| frontend | 1（浏览器侧手动确认待完成） | 1（Vite EPERM 已解决） |
| backend | 0 | 1（local pipeline 修复） |
| contract | 0 | 0 |
| async-consistency | 0 | 2（reconcile 收敛确认 + immediate GET /state 预期行为确认） |

---

## 四、总体评价

### Step 20 前端加固

> **评分：优秀。** 完美解决了上次审核的 4 项中优先级问题。Hook 拆分干净、命令路由统一、状态语义丰富、集成测试全面。测试数从 9 → 20 (+122%)。代码组织达到了 MVP 阶段的理想状态。

### Step 21 集成启动

> **评分：优秀。** `local_pipeline.py` 以最小改动解决了一个真正的集成阻塞，同时保持了 PM 的异步处理约束。测试清理加固消除了测试间污染。集成检查清单和问题追踪为后续工作提供了清晰的审计路径。7 个端点全部通过了真实 HTTP 烟雾测试。

---

## 五、当前剩余建议

| 优先级 | 建议 |
|--------|------|
| 🟡 1 | `_snapshot_user_state` / `_restore_user_state` 在多个测试文件中重复，建议提取到 `tests/conftest.py` 共享 fixture |
| 🟡 2 | 浏览器侧手动确认仍未完成（timeline `synced`、dev panel 刷新、推荐卡片交互），建议安排一次完整的 UI 手动过程 |
| 🟢 3 | README 或部署文档中补充 Vite proxy vs 生产 CORS 的说明 |
| 🟢 4 | `ChatInput.test.tsx` 仍测试旧的 `/pull` 命令路由行为（调用 `onPull`），但 `ChatInput` 已不再做这个分支——测试可能需要更新以反映当前行为 |
| 🟢 5 | 启用 Celery worker dispatch（`ENABLE_WORKER_DISPATCH=True`）做一次端到端验证，确认 Celery 路径与 local pipeline 路径行为一致 |
| 🟢 6 | Timeline 虚拟化可在有真实长时间使用场景时再实现 |

---

## 六、测试覆盖汇总

| 层次 | 测试数 | 状态 |
|------|--------|------|
| 后端 | 44 | ✅ 全部通过 |
| 前端 | 20 | ✅ 全部通过 |
| 前端构建 | — | ✅ Vite production build 通过 |
| 实际 HTTP 烟雾 | 7 端点 × 2 路径(uvicorn + proxy) | ✅ |
