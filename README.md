# Harbor Support · 企业客服与工单执行 Agent MVP

Harbor Support 是一个可运行、可测试、可重复演示的电商售后客服 Agent。它用单 Agent 理解用户诉求，通过结构化工具调用完成政策问答、订单与物流查询、物流异常建单、人工接管与 SLA 跟踪，以及需要用户明确确认的退款闭环。

业务事实与安全规则不放在 Prompt 或前端：订单归属、物流异常、可退金额、状态机、审批和幂等全部由 FastAPI 领域服务与 PostgreSQL 事务执行。

## 核心能力

- 政策问答：检索有效知识条款，返回文章、版本、条款与相关度；证据不足时拒绝猜测。
- 订单与物流：服务端解析当前用户并校验订单归属；物流异常由 36 小时停滞规则判断。
- 异常建单：在单个会话内幂等创建 `SHIPPING` 工单，关联订单、会话与物流证据；新会话会创建独立工单。
- 人工接管：工单按类型设置 P1/P2/P3 优先级与 SLA，用户可发起或撤销接管，服务端自动分派支持组并记录完整时间线。
- 坐席工作台：两个独立演示坐席共享实时人工队列，使用原子受理保护确保工单只归属首位受理人；新工单无需刷新即可进入队列，并支持断线重连、客户双向消息、“我的处理中”、内部处理记录与解决闭环。
- 客户结果回传：人工工单解决后，客户侧自动同步最终处理方案、处理人和完成时间；坐席内部处理备注保持仅坐席可见。
- 退款确认：Agent 只能创建待确认申请；确认接口重新校验身份、金额、状态与幂等键。
- 结构化事件：前端只消费 `tool_started`、`tool_completed`、`approval_required` 等事件，不解析自然语言中的业务状态。
- 持久化审计：保存对话、消息、工单、退款、工具调用、耗时、错误与关联 ID。
- 知识运营：独立运营身份可查看条款历史、发布新版本和停用条款；版本变更立即进入客服检索范围。
- 运营看板：实时汇总活动工单、人工接管、SLA 风险、退款、工具成功率与知识版本；支持按处理组和 SLA 状态下钻工单、导出当前筛选结果，并主动推送待受理与 SLA 风险告警。运营人员可确认知悉，确认人和时间持久化保存，风险升级后重新进入待确认状态。
- 自动质检：对人工坐席已解决工单执行可解释的确定性评分，检查 SLA、首次回复、内部处理记录和最终解决方案完整度，并逐单展示缺失项。
- 双运行模式：默认确定性模式无需 API Key；配置后可切换 OpenAI Agents SDK 单 Agent 模式。

## 工程结构

```text
apps/api/                 FastAPI 模块化单体
  alembic/                PostgreSQL/pgvector 迁移
  src/serviceops/
    identity/             当前用户与资源归属
    conversations/        会话、消息与状态投影
    knowledge/            知识检索、版本与来源
    orders/ shipping/     订单与确定性物流异常
    tickets/ refunds/     状态机、审批与幂等
    workbench/            坐席队列、受理、处理记录与解决
    agent/                 确定性运行器与 Agents SDK 运行器
    audit/                 工具调用脱敏审计
demo/                     Vinext/React 客户端（Sites 与 Docker 兼容）
docs/                     产品、技术、流程与交付文档
docker-compose.yml        web、api、PostgreSQL/pgvector
```

详细边界见 [架构说明](docs/architecture.md)，演示步骤见 [演示脚本](docs/demo-script.md)。

## 一键启动

环境要求：Docker Desktop 与 Docker Compose。

```bash
docker compose up --build
```

启动后访问：客户工作台 <http://localhost:3000>，坐席工作台 <http://localhost:3000/agent>，API 文档 <http://localhost:8000/docs>，健康检查 <http://localhost:8000/health>。

默认使用不依赖模型服务的确定性 Agent 模式，四个核心场景可以直接演示。

三个服务都使用 `unless-stopped` 自动恢复策略。首次执行启动命令后，只要没有手动停止项目，后续电脑重启并打开 Docker Desktop 时，数据库、后端和网页会按健康检查顺序自动恢复；等待 Docker Desktop 显示引擎运行后即可重新访问网页。

### 启用 OpenAI Agents SDK 模式

复制根目录 `.env.example` 为 `.env`，填写服务端密钥：

```env
AGENT_MODE=openai
OPENAI_API_KEY=your-server-side-key
OPENAI_MODEL=gpt-5.4-mini
```

密钥只传给 API 容器，不进入浏览器、镜像或工具调用日志。未配置密钥时系统自动使用确定性模式。

## 本地开发

后端：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".\apps\api[test]"
$env:DATABASE_URL = "sqlite:///./serviceops.db"
.\.venv\Scripts\python.exe -m uvicorn serviceops.main:app --app-dir apps/api/src --reload
```

前端：

```powershell
cd demo
pnpm install --frozen-lockfile
$env:NEXT_PUBLIC_API_URL = "http://localhost:8000"
pnpm run dev -- --host 127.0.0.1 --port 3000
```

本地测试身份通过不透明的 `X-Demo-Session` 解析，前端不能传入可信 `user_id`。种子账号“林沐”的演示令牌只用于本地环境。

## 测试与质量门禁

```powershell
.\.venv\Scripts\ruff.exe check apps/api
.\.venv\Scripts\pytest.exe apps/api/tests

cd demo
pnpm run lint
pnpm run build
pnpm run test:e2e
```

测试覆盖领域状态机、金额、归属、幂等、知识阈值、过期知识、Prompt Injection、人工接管、自动分派、双坐席受理冲突、实时队列身份与事件契约、客户与坐席双向消息、运营工单筛选、实时告警与确认幂等、人工工单自动质检、客户结果回传、内部备注隔离、SLA、API 契约、结构化事件和刷新恢复。Playwright 覆盖客户、坐席实时收单、双向工单沟通、双坐席归属、运营筛选与 CSV 导出、运营主动告警确认与刷新恢复、客服处理方案、自动质检、知识运营与质量看板场景；正式 Docker 环境使用 PostgreSQL/pgvector。

知识检索另有一组可重复的中文口语化评测，覆盖全部 12 个政策条款，每个条款至少 2 条可回答样本，并包含 6 条知识库外拒答样本：

```bash
docker compose exec -T api python -m serviceops.cli evaluate-knowledge
```

评测门禁要求可回答问题条款命中率不低于 95%，知识库外问题误答率为 0。当前固定评测集为 24/24 条款命中、6/6 正确拒答；CLI 以 JSON 输出详细指标和失败样本，未通过时返回非零退出码。

## 演示数据重置

非生产环境可重置可变业务数据：

```bash
curl -X POST http://localhost:8000/api/demo/reset -H "X-Demo-Session: demo-linmu-session"
```

重置会清理会话、消息、工单、退款、幂等与工具审计，恢复演示订单的可退金额，并把知识库恢复为固定的 `2026-07` 演示版本；客户和物流固定数据保持不变。生产环境会拒绝该接口。

## 已知限制

- 订单、物流和支付均为模拟适配器，不会调用真实平台或产生真实资金动作。
- 默认确定性运行器用于离线演示与稳定测试；Agents SDK 模式需要服务器端 OpenAI API Key。
- MVP 使用小型知识集和轻量的中文概念/关键词混合召回；PostgreSQL 已启用 pgvector 扩展与向量字段，真实 embedding 管道留待评测显示现有召回不足且接入模型服务后启用。
- 当前坐席工作台使用两个固定演示坐席并支持原子受理冲突保护，尚未接入企业账号、组织权限和排班。
- 当前运营看板支持单实例内的实时主动告警，尚未接入短信、邮件、企业 IM 等外部通知渠道或长期数据仓库。
- 当前质检使用透明的固定规则，不包含模型对语气、同理心或复杂方案合理性的主观判断。
- 暂不包含多渠道、多 Agent、消息队列或 Elasticsearch。
