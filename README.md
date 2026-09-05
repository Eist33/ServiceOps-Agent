# Harbor Support · 企业客服与工单执行 Agent MVP

Harbor Support 是一个可运行、可测试、可重复演示的电商售后客服 Agent。它用单 Agent 理解用户诉求，通过结构化工具调用完成政策问答、订单与物流查询、物流异常建单、人工接管与 SLA 跟踪，以及需要用户明确确认的退款闭环。

业务事实与安全规则不放在 Prompt 或前端：订单归属、物流异常、可退金额、状态机、审批和幂等全部由 FastAPI 领域服务与 PostgreSQL 事务执行。

## 核心能力

- 政策问答：检索有效知识条款，返回文章、版本、条款与相关度；证据不足时拒绝猜测。
- 订单与物流：服务端解析当前用户并校验订单归属；物流异常由 36 小时停滞规则判断。
- 开发账号登录：客户和后台员工从已有模拟账号登录，服务端签发有期限、可吊销的不透明会话；浏览器不再内置固定身份令牌，客服、知识运营和运营看板同时执行服务端角色校验。
- 最近订单选择：客户无需预先输入订单号；涉及订单且尚未选定时，Agent 只读查询当前客户最近 3 笔订单并等待明确选择。活动订单按会话持久化，刷新可恢复，新对话不会沿用旧订单。
- 自然语言统一入口：客户页面不再要求选择政策、订单、物流、工单或退款模块；示例问法只是发送到当前会话的普通消息。Agent 支持多诉求安全排序、活动订单指代、订单选择后自动续办，以及退款原因缺失时跨轮追问。
- 异常建单：在单个会话内幂等创建 `SHIPPING` 工单，关联订单、会话与物流证据；新会话会创建独立工单。
- 人工接管：工单按类型设置 P1/P2/P3 优先级与 SLA，用户可发起或撤销接管，服务端自动分派支持组并记录完整时间线。
- 坐席工作台：两个独立演示坐席共享实时人工队列，使用原子受理保护确保工单只归属首位受理人；新工单无需刷新即可进入队列，并支持断线重连、客户双向消息、“我的处理中”、内部处理记录与解决闭环。
- 客户结果回传：人工工单解决后，客户侧自动同步最终处理方案、处理人和完成时间；坐席内部处理备注保持仅坐席可见。
- 退款确认：Agent 只能创建待确认申请；确认接口重新校验身份、金额、状态与幂等键。
- 结构化事件：前端只消费 `tool_started`、`tool_completed`、`approval_required` 等事件，不解析自然语言中的业务状态。
- 持久化审计：保存对话、消息、工单、退款、工具调用与模型调用元数据；模型审计仅记录供应商、模型、耗时、Token、错误类型和追踪号，不保存 Prompt、回答或密钥。
- 安全可观测性：请求、Agent 事件和工具审计共享同一 `trace_id`；访问日志采用不记录请求正文与身份令牌的结构化字段，嵌套敏感字段递归脱敏，未知错误只向客户端返回可追踪的通用错误。
- 知识运营：独立运营身份可查看条款历史、发布新版本和停用条款；版本变更立即进入客服检索范围。
- 运营看板：实时汇总活动工单、人工接管、SLA 风险、退款、工具成功率与知识版本；支持按处理组和 SLA 状态下钻工单、导出当前筛选结果，并主动推送待受理与 SLA 风险告警。运营人员可确认知悉，确认人和时间持久化保存，风险升级后重新进入待确认状态。
- 自动质检：对人工坐席已解决工单执行可解释的确定性评分，检查 SLA、首次回复、内部处理记录和最终解决方案完整度，并逐单展示缺失项。
- 客户满意度：人工工单解决后，工单所属客户可提交一次 1–5 星评价与可选意见；评价持久化到服务端并进入运营质量看板，重复请求保持幂等，其他客户或未解决工单无法评价。
- 双运行模式：默认确定性模式无需 API Key；配置后可通过通用适配层使用 DeepSeek Responses API。模型超时、限流或熔断且尚未发生写操作时自动降级，退款确认等高风险边界不交给模型。

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
    agent/                 确定性运行器、通用模型适配与 Agents SDK 流式运行器
    audit/                 工具与模型调用脱敏审计
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

Windows 用户也可以在 Docker Desktop 启动后直接运行：

```bat
scripts\start-product.cmd
```

不希望自动打开浏览器时使用 `scripts\start-product.cmd --no-browser`。该入口使用 Windows 命令提示符，不依赖 PowerShell。

仍需使用 PowerShell 的用户也可以运行：

```powershell
.\scripts\start-product.ps1
```

脚本会等待数据库与 API 健康后再打开客户工作台；只想启动服务、不自动打开浏览器时使用 `.\scripts\start-product.ps1 -NoBrowser`。

启动后访问：客户服务入口 <http://localhost:3000>，客服后台 <http://localhost:3000/staff/agent>，知识运营 <http://localhost:3000/staff/knowledge>，运营看板 <http://localhost:3000/staff/operations>，API 文档 <http://localhost:8000/docs>，健康检查 <http://localhost:8000/health>。客户页面不展示任何后台入口；`/agent`、`/knowledge` 和 `/operations` 旧地址仅保留兼容跳转。

开发环境登录账号如下，统一默认密码为 `serviceops`，可通过 `DEMO_LOGIN_PASSWORD` 修改：客户“林沐”“周远”；客服坐席“沈清禾”“陆川”；知识与运营管理员“许知夏”。客户账号只能进入客户服务，客服坐席只能进入客服工作台，知识与运营管理员只能进入知识运营和运营看板。

默认使用不依赖模型服务的确定性 Agent 模式。客户可以直接输入“帮我查一下快递”，系统会展示模拟客户最近 3 笔订单；选择后会继续刚才的请求，也可以使用“这个订单”查询物流、创建工单或发起待确认退款。输入“我要转人工客服”或“刚才的工单处理了吗”时，Agent 会使用当前会话工单，不会跨会话查找。

三个服务都使用 `unless-stopped` 自动恢复策略。首次执行启动命令后，只要没有手动停止项目，后续电脑重启并打开 Docker Desktop 时，数据库、后端和网页会按健康检查顺序自动恢复；等待 Docker Desktop 显示引擎运行后即可重新访问网页。

### 启用 DeepSeek 模型模式

最简单、安全的本机部署方式是在 Docker Desktop 已启动后运行：

```powershell
.\scripts\deploy-local-deepseek.ps1
```

脚本会要求在终端中输入 DeepSeek API Key，输入内容不会显示。密钥只写入已被 Git 忽略的本机 `.env`，随后自动构建 Docker、升级数据库、执行离线质量门禁和两条真实模型烟雾测试。成功后打开 <http://127.0.0.1:3000/> 即可使用。

首次部署或需要验证 Docker 冷启动时使用：

```powershell
.\scripts\deploy-local-deepseek.ps1 -ColdStart
```

需要执行全部 70 条真实模型编排评测时使用下面的命令。该模式会产生约 70 次对话及其工具回合的真实 API 调用、需要数分钟，并产生相应的模型费用：

```powershell
.\scripts\deploy-local-deepseek.ps1 -EvaluateFullModel
```

也可以手动复制根目录 `.env.example` 为 `.env`，填写服务端密钥：

```env
AGENT_MODE=model
MODEL_PROVIDER=deepseek
MODEL_API_STYLE=responses
MODEL_BASE_URL=https://api.deepseek.com
MODEL_NAME=deepseek-v4-flash
MODEL_API_KEY=your-server-side-deepseek-key
```

重新执行 `docker compose up -d --build --wait` 后生效。密钥只在运行时传给 API 容器，不进入浏览器包、镜像、业务表、工具日志或模型审计。`AGENT_MODE=deterministic` 始终可作为离线模式；如果选择模型模式但密钥缺失或模型服务暂时不可用，系统会发出 `model_fallback` 事件并在安全条件满足时切换到确定性运行器。模型已产生写操作或已向客户输出部分内容后不会盲目重放请求。

配置完成后可运行 `.\scripts\verify-model-provider.ps1 -ResetAfter`，受控验证真实模型的流式文本、政策检索、订单查询和物流工具调用；脚本只检查容器中是否已配置密钥，不读取或输出密钥值。`-ResetAfter` 会在通过后重置演示数据，不希望清理当前演示记录时请省略该参数。

详细部署、回滚和生产环境注意事项见 [部署指南](docs/deployment.md)。不要把 API Key 粘贴到聊天、截图、Git 提交或浏览器代码中。

不使用 PowerShell 时，可以在根目录 `.env` 中安全配置模型环境变量，然后运行 `scripts\verify-release.cmd --verify-model`。

兼容期仍支持原来的 `AGENT_MODE=openai`、`OPENAI_API_KEY` 和 `OPENAI_MODEL` 配置，但订单归属、建单幂等、退款金额与最终确认仍由同一套服务端领域规则控制。

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

浏览器通过开发账号登录取得短期 Bearer 会话，原始令牌只保存在当前标签页的 `sessionStorage`，数据库仅保存 SHA-256 摘要并支持过期和退出吊销。兼容测试仍可使用旧演示请求头，但前端不再内置固定令牌，也不能传入可信 `user_id`。生产环境关闭开发认证入口后，固定演示请求头全部失效。

## 测试与质量门禁

```powershell
.\.venv\Scripts\ruff.exe check apps/api
.\.venv\Scripts\pytest.exe apps/api/tests

cd demo
pnpm run lint
pnpm run build
pnpm run test:e2e
```

交付前可用一条命令执行 Docker 构建、可选冷启动、迁移版本、四个页面、API 健康、全部自动化测试和演示数据重置：

```bat
scripts\verify-release.cmd --cold-start
```

该 CMD 入口会执行后端、前端、Playwright、知识评测和 70 条离线 Agent 编排评测，不依赖 PowerShell。只运行代码级完整测试时使用 `scripts\verify.cmd`。

原 PowerShell 入口仍然保留：

```powershell
.\scripts\verify-release.ps1 -ColdStart
```

如果本机已经安全配置 DeepSeek Key，可以加上 `-VerifyModelProvider` 验证真实流式回答和工具调用；再加 `-EvaluateFullModel` 会运行完整的 70 条真实模型发布评测。

测试覆盖领域状态机、金额、归属、幂等、知识阈值、过期知识、Prompt Injection、人工接管、自动分派、双坐席受理冲突、实时队列身份与事件契约、客户与坐席双向消息、运营工单筛选、实时告警与确认幂等、人工工单自动质检、客户满意度归属与单次提交、客户结果回传、内部备注隔离、SLA、API 契约、结构化事件和刷新恢复。Playwright 覆盖客户、坐席实时收单、双向工单沟通、双坐席归属、运营筛选与 CSV 导出、运营主动告警确认与刷新恢复、客服处理方案、客户满意度、自动质检、知识运营与质量看板场景；正式 Docker 环境使用 PostgreSQL/pgvector。

知识检索另有一组可重复的中文口语化评测，覆盖全部 12 个政策条款，每个条款至少 2 条可回答样本，并包含 6 条知识库外拒答样本：

```bash
docker compose exec -T api python -m serviceops.cli evaluate-knowledge
```

评测门禁要求可回答问题条款命中率不低于 95%，知识库外问题误答率为 0。当前固定评测集为 24/24 条款命中、6/6 正确拒答；CLI 以 JSON 输出详细指标和失败样本，未通过时返回非零退出码。

Agent 编排另有 70 条隔离执行的中文真实表达样本，覆盖政策、订单、物流、建单、退款、人工接管、多订单、多诉求、上下文、新会话、重复请求、他人订单、Prompt Injection、工具失败和高风险确认：

```bash
docker compose exec -T api python -m serviceops.cli evaluate-agent
```

门禁要求主要诉求和工具选择正确率不低于 95%、工具参数有效率不低于 98%，并要求多订单选择前写入、他人数据泄露、未经确认退款、失败伪装成功和客户后台工具暴露全部为 0。当前确定性基线为 70/70 通过。配置模型模式后可使用 `--runtime model` 对同一语料执行真实提供方评测；真实模型评测强制关闭自动降级，避免用本地结果掩盖模型失败。

## 演示数据重置

非生产环境可重置可变业务数据：

```bash
curl -X POST http://localhost:8000/api/demo/reset -H "X-Demo-Session: demo-linmu-session"
```

重置会清理会话、消息、工单、退款、客户满意度、幂等、工具审计与模型调用审计，恢复演示订单的可退金额，并把知识库恢复为固定的 `2026-07` 演示版本；客户和物流固定数据保持不变。生产环境会拒绝该接口。

## 已知限制

- 订单、物流和支付均为模拟适配器，不会调用真实平台或产生真实资金动作。
- 默认确定性运行器用于离线演示与稳定测试；DeepSeek 模型模式需要服务端 API Key。仓库永远不包含真实密钥；首次在一台电脑上部署时，需要在本机输入 Key 并完成受控联网验收。
- MVP 使用小型知识集和轻量的中文概念/关键词混合召回；PostgreSQL 已启用 pgvector 扩展与向量字段，真实 embedding 管道留待评测显示现有召回不足且接入模型服务后启用。
- 当前已实现开发账号登录、会话过期/吊销和基础角色隔离；尚未接入企业 SSO、客服组织数据范围和排班。生产客户身份计划通过淘宝、小红书、闲鱼等平台的官方授权接口建立映射，不使用页面抓取或让模型决定客户归属。
- 当前运营看板支持单实例内的实时主动告警，尚未接入短信、邮件、企业 IM 等外部通知渠道或长期数据仓库。
- 当前质检使用透明的固定规则，不包含模型对语气、同理心或复杂方案合理性的主观判断。
- 当前客户满意度为每个已解决工单一次 1–5 星评价，不包含追评、修改评价或独立问卷编排。
- 暂不包含多渠道、多 Agent、消息队列或 Elasticsearch。

后续生产认证、真实业务适配器、基础设施、灾备和试点发布的实施顺序见 [生产化开发流程](docs/企业客服与工单执行Agent_生产化开发流程_v1.0.md)。
身份与电商平台边界见 [ADR-0001：开发账号认证与多电商平台身份接入](docs/ADR-0001-开发账号认证与多电商平台身份接入.md)。
