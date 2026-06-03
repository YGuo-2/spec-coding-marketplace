# Design-First 完整使用示例

本文档展示了一个端到端的 Design-First 工作流示例，
演示如何使用 spec-coding 技能从技术设计出发，依次生成设计、需求与任务清单。

---

## 场景：按既定事件驱动方案为订单系统增加出站事件能力

### 路由判断

**用户输入：**
> 我们已经决定用 outbox + worker 的方案给订单系统发出站事件。先按这个技术方案做 spec，再决定具体需求和任务。

**智能体响应：**

## 🧭 Spec 路由决定

- 路径：Feature / Design-First
- Design-First 粒度：High Level Design
- 原因：用户已给出既定技术方案，并要求先从技术设计出发
- 下一步：Design-First 澄清

---

### 状态 A-D：Design-First 设计起点审视与澄清

**智能体响应：**

## 🧱 Design-First 澄清清单

- 设计粒度：High Level Design

在进入 Design-First 规范阶段之前，我需要确认以下问题：

1. 现有订单服务、消息 broker、消费方分别是什么技术栈？
2. 哪些接口契约和数据库表结构已经锁定，不能修改？
3. 出站事件需要满足哪些可靠性、幂等性和延迟约束？
4. 这次设计明确不处理哪些能力，例如事件重放、跨区域复制？
5. 是否已有 ADR、拓扑图或监控指标作为设计输入？

**用户回复：**
> 1. 订单服务是 Node.js，broker 是 Kafka  
> 2. 订单创建接口不能改，现有 orders 表可以加字段但不能改主键  
> 3. 至少一次投递，可接受 5 秒内延迟，消费方自己做幂等  
> 4. 这次不做事件重放  
> 5. 有 ADR，核心决策就是 outbox + worker

---

### 状态 B-D：Design-First 规范工件生成

智能体生成以下三个文件：

#### docs/specs/design.md（节选）

```markdown
> **设计粒度：** High Level Design

## 4. 方案设计

### 4.2 拓扑 / 调用链

订单 API -> 订单服务 -> orders / outbox 表 -> worker -> Kafka
```

#### docs/specs/requirements.md（节选）

```markdown
### REQ-001: 订单创建后发布出站事件

**作为** 下游订阅服务，**我希望** 在订单创建成功后收到标准化事件，
**以便** 异步处理履约与通知流程。

- **AC-001.1:**
  - **GIVEN** 订单创建成功
  - **WHEN** outbox worker 处理待发送记录
  - **THEN** Kafka 中应出现符合约定 schema 的订单创建事件
```

#### docs/specs/tasks.md（节选）

```markdown
- [ ] **T-001:** 固化 outbox 持久化与 worker 基础约束
  - ✅ 验证标准：设计中的事务边界与投递路径被落地

- [ ] **T-002:** 实现订单创建后的 outbox 写入与事件发布路径
  - ✅ 验证标准：同时满足 design.md 和 requirements.md 的约束
```

**智能体输出：**
> ✅ Design-First 规范工件生成完毕。请审查 `docs/specs/design.md`、`docs/specs/requirements.md` 和 `docs/specs/tasks.md`。  
> 确认无误后，请回复 **"批准 design-first 规范，启动执行"**。

**用户回复：**
> 批准 design-first 规范，启动执行

---

### 状态 C：受控代码实施

**智能体：** 📌 锁定任务 **T-001**：固化 outbox 持久化与 worker 基础约束

*(智能体会先实现第一个任务，并验证它同时满足 `design.md` 与 `requirements.md`。)*

---

## 关键要点总结

1. **这是先设计后需求，不是把 Requirements-First 换个名字**
2. **必须先判定 High Level Design 还是 Low Level Design**
3. **`requirements.md` 必须从 `design.md` 派生，不能越界**
4. **任务清单既要忠实设计，也要忠实派生需求**
