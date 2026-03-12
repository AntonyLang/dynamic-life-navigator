# Frontend Design & Interaction Logic V2

前端定位仍然是 Thin Client，但不再只写“体感”，而是和后端接口严格对齐。

## 1. 前端总体原则
- 轻交互、低维护、不承担业务真相
- 所有状态以 `/api/v1/state` 为准
- 所有建议以 recommendation_id 为准，方便反馈回传
- 前端必须支持空态、失败态、重试态，不假设后端永远成功

---

## 2. 桌面端（uTools / Raycast 类插件）
## 2.1 定位
适合学习、写代码、做项目时的快速输入与拉取建议。

## 2.2 页面结构
### 顶部状态栏
- Mental Energy
- Physical Energy
- Focus Mode
- 最近更新时间

首次打开或激活窗口时调用：
- `GET /api/v1/state`

### 主消息区
展示：
- 用户消息
- 助手回复
- 推荐消息卡片
- 系统提示（如解析失败、无候选）

### 底部输入区
支持：
- 文本输入
- 快捷命令 `/pull`
- 快捷命令 `/brief`
- 粘贴截图（MVP 先只提示“已收到图片，暂未解析”也可）

---

## 3. 桌面端核心交互
## 3.1 普通记录流
1. 用户发送文本
2. 前端调用 `POST /api/v1/chat/messages`
3. 发送中展示本地 optimistic message
4. 返回成功后：
   - 刷新状态栏
   - 展示 `assistant_reply`
5. 若 `suggest_next_action = true`，显示“要不要顺手看下建议”按钮

## 3.2 Pull 建议流
触发方式：
- 输入 `/pull`
- 输入自然语言“现在适合干嘛”
- 点击“帮我选”按钮

调用：
- `GET /api/v1/recommendations/pull`

前端渲染：
- 若 `items.length > 0`：展示建议卡片
- 若 `empty_state = true`：展示 fallback 文案和二级筛选入口

建议卡片至少包含：
- 标题
- 一句话建议
- 反馈按钮：采纳 / 略过 / 换一个

反馈调用：
- `POST /api/v1/recommendations/{recommendation_id}/feedback`

## 3.3 简报流
触发：
- 输入 `/brief`
- 点击“进度简报”按钮

调用：
- `GET /api/v1/recommendations/brief`

渲染：
- 活跃项目数
- 价值流数
- 紧急节点
- 每个节点的 next hint

---

## 4. 移动端（企业微信/微信机器人）
## 4.1 定位
适合通勤、户外、碎片时间的语音输入与有限 Push。

## 4.2 交互形式
MVP 推荐：
- 以聊天会话为主
- 不强依赖复杂菜单
- 菜单按钮仅做快捷入口，不承载复杂信息架构

建议菜单：
- `帮我选` -> Pull 建议
- `状态重置` -> 打开状态重置指令
- `进度简报` -> 拉取 brief

## 4.3 Push 设计
Push 消息必须足够短，并且可反馈。

一条合格 Push 至少包含：
- 为什么现在推（轻微解释）
- 建议本身
- 一个可执行动作

例如：
“你刚结束高强度运动，今晚不太适合再上体力活。期中项目离截止只剩 4 天，要不要先把输入接口补完 20 分钟？”

Push 交互反馈：
- 采纳
- 稍后提醒
- 今天别推了

---

## 5. 前端状态机建议
## 5.1 消息发送状态
- idle
- sending
- success
- failed

## 5.2 推荐卡片状态
- loading
- ready
- empty
- feedback_submitting
- feedback_done
- feedback_failed

## 5.3 状态栏状态
- initial_loading
- ready
- stale
- error

说明：
- 若 `/api/v1/state` 超时，不阻塞消息发送，但顶部状态显示 stale

---

## 6. 空态 / 异常态设计
## 6.1 无候选节点
展示：
- fallback_message
- 二级筛选建议：
  - “只看 20 分钟以内”
  - “只看不动脑的”
  - “只看在室内能做的”

## 6.2 解析失败
展示：
- “我先记下原话了，但这次没完全看懂。你可以直接说想休息、想出门还是想推进项目。”

## 6.3 网络失败
展示：
- 本地错误 toast
- 消息保留重试按钮

---

## 7. 技术实现建议
### 桌面端
- React 或 Vue 3 都可
- 使用轻状态管理（Zustand / Pinia）即可
- recommendation_id、request_id 必须进入前端日志

### 移动端
- 若追求稳定性，优先企业微信官方接口
- Wechaty 仅建议用于个人试验，不作为正式稳定方案的默认路线

---

## 8. 埋点建议
前端最少上报：
- 消息发送成功/失败
- Pull 请求发起/成功/空结果
- 推荐卡片曝光
- 推荐反馈点击
- Push 消息点击/忽略
