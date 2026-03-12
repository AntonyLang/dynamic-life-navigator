# Revision Summary

本轮修订的目标是把原始 PM 草案从“概念正确”提升到“可进入开发设计”。

## 本次新增的关键内容
1. 明确 MVP 边界与非目标
2. 统一领域模型：state / node / event / recommendation / feedback
3. 补齐 API 契约：请求、响应、错误码、幂等与鉴权
4. 重构数据库：新增 recommendation 与 annotation 相关表
5. 明确 Push 治理：触发条件、抑制条件、cooldown 与反馈闭环
6. 补充前端空态、异常态、反馈态
7. 架构从“Agent 角色描述”升级为“可实现的 service + worker 分层”
8. 场景文档改造成验收用例

## 建议开发顺序
1. 落表与 API 骨架
2. 实现聊天输入 + state 更新
3. 实现 Pull 推荐
4. 实现 feedback 闭环
5. 接入一个 webhook 源
6. 补 enrichment / compression / push
