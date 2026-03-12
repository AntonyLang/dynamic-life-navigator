# User Scenarios & Validation Cases V2

本文档将原“故事型场景”升级为可验收的业务用例。

## 用例 1：高脑力消耗后触发 Pull 推荐
### 前置条件
- 当前时间：周六 15:00
- user_state：
  - mental_energy = 75
  - physical_energy = 90
  - focus_mode = focused
- action_nodes 中存在：
  1. CSAPP Archlab 推进（mental 80 / physical 10）
  2. 沿海骑行 40 分钟（mental 10 / physical 60）
  3. 听新歌放空 20 分钟（mental 5 / physical 5）

### 输入
用户消息：
“实验终于调通了，脑子要烧干了，现在一点代码都不想看。”

### 预期系统行为
1. 创建一条 event_logs
2. Data Agent 解析为高脑力消耗事件
3. 更新 user_state：
   - mental_energy 降至低位，如 10~25 区间
   - physical_energy 基本不变
   - focus_mode 更新为 tired
4. 若用户继续发起 Pull，请求候选过滤时：
   - CSAPP Archlab 被过滤
   - 骑行 / 听歌进入候选
5. 若存在有效 annotation：
   - 天气信息可增强骑行建议
   - 新歌单可增强听歌建议

### 预期输出
- 返回 1~2 条建议
- 文案不得继续强推编码类任务
- 若引用实时情报，必须来自未过期 annotation

### 验收点
- recommendation_records 有落库
- candidate_node_ids 包含骑行/听歌，不包含 Archlab
- 用户可对建议做 feedback

---

## 用例 2：外部运动事件后触发 Push 评估
### 前置条件
- 当前时间：周二 20:00
- user_state：
  - mental_energy = 70
  - physical_energy = 65
- action_nodes：
  1. 力量训练（physical 75）
  2. 期中项目接口完善（mental 55, ddl 紧迫）
- 最近 4 小时无 Push
- 不在免打扰窗口内

### 输入
Strava webhook 到达，表示刚完成高强度运动。

### 预期系统行为
1. webhook 验签成功
2. event_logs 记录原始 payload 与 external_event_id
3. state 更新：
   - physical_energy 明显下降，如降到 20~30
4. 触发 evaluate_push_opportunities
5. 候选筛选时：
   - 力量训练被过滤
   - 期中项目保留
6. push_policy_engine 检查通过，允许推送

### 预期输出
- 生成一条 push recommendation
- 文案表达“今晚不建议再做体力活，但可以推进项目的一小步”

### 验收点
- recommendation_records.mode = push
- delivery_status 成功记录
- 若 webhook 重复投递，不应重复推送

---

## 用例 3：价值流节点因长期未触达而被重新激活
### 前置条件
- 节点：增肌与体态改善（drive_type = value）
- 最近 3 天无相关事件
- 压缩任务运行后上调该节点长期价值权重
- enrichment 抓取到一条未过期核心训练教程 annotation

### 输入
用户发起 Pull：
“这会儿挺无聊的，有啥建议？”

### 预期系统行为
1. 读取当前 state
2. 在候选排序中给予“长期未触达但值得恢复”的适度加权
3. 若当前体力条件允许，则该节点可进入前列
4. renderer 引用教程 annotation，但不得夸大为“你一定会喜欢”这类无依据结论

### 预期输出
- 建议 20 分钟可执行训练
- 文案体现“重新捡起来”而不是强硬指令

### 验收点
- 排序分中可见 long_term_value_score 或 stale_recovery_bonus
- annotation 在有效期内

---

## 用例 4：无候选时的优雅降级
### 前置条件
- user_state：mental_energy = 10, physical_energy = 10
- 所有 active 节点要求均高于当前状态，或都在 cooldown 中

### 输入
用户发起 Pull：
“现在做什么比较合适？”

### 预期系统行为
1. 候选筛选后为空
2. 不强行调用 LLM 胡编建议
3. 返回 fallback_message

### 预期输出
- 明确告诉用户当前没有高置信度建议
- 提供二级引导，如“想看 10 分钟内、完全不动脑的事吗”

### 验收点
- response.empty_state = true
- recommendation_records 仍落库，selected_node_ids 为空

---

## 用例 5：Push 被抑制
### 前置条件
- 当前用户在 do_not_disturb_until 内，或 2 小时内刚收到过 Push
- 同时存在一个中等置信度候选

### 输入
新 webhook 到达，理论上可触发推荐

### 预期系统行为
1. evaluate_push_opportunities 被触发
2. push_policy_engine 检查抑制条件
3. 本次 recommendation_records 可记录为 skipped，但不实际发送

### 预期输出
- 无外发消息
- 保留审计信息，说明是因抑制策略跳过

### 验收点
- delivery_status = skipped
- rendered_content 可为空或仅保留内部摘要

---

## 通用验收要求
所有用例都应检查：
- request_id / trace_id 可追踪
- 关键 event / recommendation 已落库
- 失败时存在 fallback 或错误提示，而非无响应
