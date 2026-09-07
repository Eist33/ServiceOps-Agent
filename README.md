# Harbor Support · 企业客服与工单执行 Agent MVP

Harbor Support 是一个可运行、可测试、可重复演示的电商售后客服 Agent。它用单 Agent 理解用户诉求，通过结构化工具调用完成政策问答、订单与物流查询、物流异常建单、人工接管与 SLA 跟踪，以及需要用户明确确认的退款闭环。

业务事实与安全规则不放在 Prompt 或前端：订单归属、物流异常、可退金额、状态机、审批和幂等全部由 FastAPI 领域服务与 PostgreSQL 事务执行。

## 核心能力

- 政策问答：检索有效知识条款，返回文章、版本、条款与相关度；证据不足时拒绝猜测。
- 订单与物流：服务端解析当前用户并校验订单归属；物流异常由 36 小时停滞规则判断。
- 开发账号登录：客户和后台员工从已有模拟账号登录，服务端签发有期限、可吊销的不透明会话；浏览器不再内置固定身份令牌，客服、知识运营和运营看板同时执行服务端角色校验。
- 闲鱼本地实验连接：客服坐席可在后台打开用户可见的官方页面，并在明确告知后选择本地固定页面 A/B 验证连接、刷新恢复、失效关闭、账号切换和退出清除；不读取或保存手机号、验证码、Cookie、Token，也不调用闲鱼 API。
- 闲鱼聊天列表只读映射：已连接的本地固定页面支持用户手动刷新最近会话列表，最多显示 20 条并映射头像引用、昵称、最近消息摘要/时间、未读数、置顶和静音状态；字段未知显示 `UNKNOWN`，页面变化、归属不明、字段缺失过多或连接失效时失败关闭，结果只保留在当前标签页。
- 闲鱼会话详情只读映射：点击已确认的聊天列表项后读取最近最多 50 条历史消息；文本和系统消息保留受控文本，图片、商品卡、订单卡及未知类型显示“暂不支持的消息类型”占位；乱序消息稳定排序、相同内容重复消息合并、冲突消息失败关闭，详情仅绑定当前连接与当前会话，不提供任何发送或订单操作。
- 9B-5 人工审批回复草稿与发送意图：仅针对当前明确选中的会话生成绑定连接/账号/会话/页面版本/读取时间的本地草稿；`SUPPORT_AGENT` 必须人工预览、审核并二次确认。系统只记录可审计的本地 `send-intent`，状态固定为 `SEND_BLOCKED_NOT_CONFIGURED`，不发起网络请求、不自动点击或发送；用户必须在官方闲鱼前台手动完成发送。
- 9B-6 Chrome/Edge 用户控制浏览器桥接：提供共用的 Manifest V3 扩展，只在用户明确点击后读取本地固定页面中明确选中的可见会话，并把严格白名单草稿交给本地工作台预览；默认 `USER_CONTROLLED / NOT_CONFIGURED`，不读取或保存验证码、密码、Cookie、Token，不调用网络、不后台轮询、不自动点击发送。
- 官方只读适配器准入门禁：淘宝、小红书、闲鱼共用平台无关的身份/订单/物流协议和 12 项官方证据检查；资质、文档、沙箱、能力或运行时状态缺失时保持 `NOT_CONFIGURED`，不发起外部请求。当前仅完成本地门禁，未接入真实平台。
- 阶段 10 外部写入准入门禁：将工单写入、webhook 和退款沙箱能力与 9C 依赖、沙箱合同、outbox/幂等/对账、客户确认、人工审批、监控和回滚证据分开审查；未配置时为 `NOT_CONFIGURED`，未共同批准时为 `NOT_APPROVED`，即使候选准入也保持 `READY_FOR_SANDBOX` 且不发起外部请求。当前未注册外部写入适配器。
- 阶段 11 生产基础设施准入门禁：将托管数据库、Secret Manager、HTTPS/域名、可观测性、外部告警、共享运行时状态和备份恢复能力与安全配置、恢复/回滚演练及 SLO 负责人审批分开审查；缺配置为 `NOT_CONFIGURED`，缺审批为 `NOT_APPROVED`，全齐也仅为 `READY_FOR_PRODUCTION_REVIEW` 且不创建外部资源。当前未接入生产基础设施。
- 阶段 12 真实模型发布与试点准入门禁：将模型版本、Prompt/工具/知识版本、70 条评测、脱敏样本、安全计数、预算、人工接管、退款审批、回滚和角色/租户/连接/账号/会话/标签页绑定分开审查；缺配置为 `NOT_CONFIGURED`，缺证据或共同审批为 `NOT_APPROVED`，全齐也仅为 `READY_FOR_PILOT_REVIEW` 且不发起模型请求、不打开试点流量。当前未接入真实模型 Key 或试点平台。
- 最近订单选择：客户无需预先输入订单号；涉及订单且尚未选定时，Agent 只读查询当前客户最近 3 笔订单并等待明确选择。活动订单按会话持久化，刷新可恢复，新对话不会沿用旧订单。
- 自然语言统一入口：客户页面不再要求选择政策、订单、物流、工单或退款模块；示例问法只是发送到当前会话的普通消息。Agent 支持多诉求安全排序、活动订单指代、订单选择后自动续办，以及退款原因缺失时跨轮追问。
- 异常建单：在单个会话内幂等创建 `SHIPPING` 工单，关联订单、会话与物流证据；新会话会创建独立工单。
- 人工接管：工单按类型设置 P1/P2/P3 优先级与 SLA，用户可发起或撤销接管，服务端自动分派支持组并记录完整时间线。
- 坐席工作台：两个独立演示坐席共享实时人工队列，使用原子受理保护确保工单只归属首位受理人；新工单无需刷新即可进入队列，并支持断线重连、客户双向消息、“我的处理中”、内部处理记录与解决闭环。
- 客户结果回传：人工工单解决后，客户侧自动同步最终处理方案、处理人和完成时间；坐席内部处理备注保持仅坐席可见。
- 退款确认：Agent 只能创建待确认申请；确认接口重新校验身份、金额、状态与幂等键。
- 结构化事件：前端只消费 `tool_started`、`tool_completed`、`approval_required` 等事件，不解析自然语言中的业务状态。
- 持久化审计：保存对话、消息、工单、退款、工具调用与模型调用元数据；模型审计仅记录供应商、模型、耗时、Token、错误类型和追踪号，不保存 Prompt、回答或密钥。
- 账号生命周期与保留期限：后台登出、认证失效和闲鱼账号切换会清除当前标签页的全部实验数据；服务端按 7/30/180/365 天可控时钟删除到期正文、即时删除失效会话，并将安全审计匿名化且记录清理运行摘要。
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
      release.py          Agent 发布、工具能力矩阵与兼容性绑定
      context.py          上下文来源、预算、截断和敏感字段治理
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

Windows 用户也可以直接双击新的 Docker 一键入口：

```bat
scripts\start-serviceops.cmd
```

它会检查 Docker Engine，执行 `docker compose up -d --build --wait`，核对 `postgres`、`api`、`web` 的 Compose healthcheck，并在成功后打开 <http://localhost:3000/staff/channel>。停止服务时双击：

```bat
scripts\stop-serviceops.cmd
```

停止入口只执行 `docker compose stop`，不会删除 `serviceops-postgres` 数据卷。路径包含空格、重复启动和重复停止均在脚本契约中覆盖；失败时脚本会提示 `docker compose ps` 与 `docker compose logs --tail=100 postgres api web`。完整双击、成功/失败预期和 Docker-only 验收见 [Docker 一键启动与停止](docs/Docker一键启动与停止.md)。

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

启动后访问：客户服务入口 <http://localhost:3000>，客服后台 <http://localhost:3000/staff/agent>，渠道账号 / 闲鱼实验连接 <http://localhost:3000/staff/channel>，知识运营 <http://localhost:3000/staff/knowledge>，运营看板 <http://localhost:3000/staff/operations>，API 文档 <http://localhost:8000/docs>，健康检查 <http://localhost:8000/health>。客户页面不展示任何后台入口；`/agent`、`/knowledge` 和 `/operations` 旧地址仅保留兼容跳转。

开发环境登录账号如下，统一默认密码为 `serviceops`，可通过 `DEMO_LOGIN_PASSWORD` 修改：客户“林沐”“周远”；客服坐席“沈清禾”“陆川”；知识与运营管理员“许知夏”。客户账号只能进入客户服务，客服坐席只能进入客服工作台和渠道账号实验，知识与运营管理员只能进入知识运营和运营看板。

客服坐席进入 `/staff/channel` 后，先点击“打开官方闲鱼页面”并由本人完成可见登录，再阅读并同意实验告知。自动化验收使用本地固定页面，不触发真实短信或登录；真实页面没有可信身份桥接时必须点击“当前账号无法确认，停止连接”，系统保持失败关闭。连接、已确认聊天列表、会话详情和回复工作流只写入当前标签页的 `sessionStorage`，另有一个不透明标签页绑定用于阻止草稿跨标签页复用；客服后台登出、认证失效、重新登录、实验连接退出或账号切换都会清除旧值。连接边界见 [9B-1：可见登录与本地会话边界](docs/9B-1-可见登录与本地会话边界.md)，聊天列表输入输出、失败门禁和逐步验收见 [9B-2：聊天列表只读映射](docs/9B-2-聊天列表只读映射.md)，会话详情输入输出、消息占位和逐步验收见 [9B-3：会话详情只读映射](docs/9B-3-会话详情只读映射.md)，账号切换、删除、保留期限和非开发者验收见 [9B-4：账号切换、删除和保留期限](docs/9B-4-账号切换删除和保留期限.md)，人工审批草稿、撤回、发送意图和固定页面验收见 [9B-5：人工审批回复草稿与发送意图](docs/9B-5-人工审批回复草稿与发送意图.md)，Chrome/Edge 扩展桥接、Docker 验收和手工加载见 [9B-6：Chrome/Edge 用户控制浏览器桥接](docs/9B-6-Chrome-Edge用户控制浏览器桥接.md)。

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
pnpm run test:unit
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

测试覆盖领域状态机、金额、归属、幂等、知识阈值、过期知识、Prompt Injection、人工接管、自动分派、双坐席受理冲突、实时队列身份与事件契约、客户与坐席双向消息、运营工单筛选、实时告警与确认幂等、人工工单自动质检、客户满意度归属与单次提交、客户结果回传、内部备注隔离、SLA、API 契约、结构化事件和刷新恢复。Playwright 覆盖客户、坐席实时收单、双向工单沟通、双坐席归属、运营筛选与 CSV 导出、运营主动告警确认与刷新恢复、客服处理方案、客户满意度、自动质检、知识运营与质量看板，以及 9B-1 闲鱼本地连接的显式同意、固定页面 A/B、刷新恢复、失败关闭、标签页隔离、后台登出清除和退出清除；9B-2 领域测试覆盖最近 20 条、稳定排序、未读/置顶/静音、空列表、未知字段、分页截断、页面变化、身份不明、会话失效、重复读取、失败不覆盖成功缓存和 A/B 隔离，Playwright 覆盖手动刷新与刷新恢复；9B-3 领域测试覆盖文本/系统/未知消息、乱序、重复与冲突、空历史、50 条截断、失效、页面变化、旧连接重放、跨账号和伪造会话，Playwright 覆盖点击详情、刷新恢复、无写请求/无写入口及 A/B 切换清除；9B-4 后端测试覆盖 7/30/180/365 天边界、消息/工单子记录/模型与工具审计跨客户清理、安全审计匿名化、失效会话即时删除、幂等运行和诊断/备份不落在线表；9B-5 单元与固定页面 E2E 覆盖草稿绑定、人工审核、二次确认、撤回、过期、上下文/页面版本失败关闭、重复动作、跨标签页隔离和零外部请求；9B-6 直接 Node 契约测试覆盖扩展权限、显式读取、当前可见会话选择、来源/账号/连接/会话/标签页绑定、过期、重复动作、工作台桥接和 no-send/no-network invariant；9C 契约测试覆盖三平台缺失证据的 `NOT_CONFIGURED`、只读能力声明、provider 隔离、完整证据门禁和无外部请求；阶段 10 契约测试覆盖默认未配置、配置后未审批、逐项证据与能力审批缺失、请求开关失败关闭、provider 隔离、候选准入幂等和零外部请求；阶段 11 契约测试覆盖默认未配置、非 production 环境、公网数据库端口、外部资源开关、逐项证据与能力审批缺失、候选评审幂等和零基础设施副作用；正式 Docker 环境使用 PostgreSQL/pgvector。

### 9B-6 Chrome/Edge 本地扩展验收

扩展契约和本地固定页面验收统一使用 Docker Compose；Docker Engine 不可用时只能报告环境阻塞，不能把宿主机结果冒充 Docker 验收：

```bash
docker compose -f docker-compose.extension.yml config --quiet
docker compose -f docker-compose.extension.yml up -d --wait extension-fixture
docker compose -f docker-compose.extension.yml ps
docker compose -f docker-compose.extension.yml run --rm extension-contract
docker compose -f docker-compose.extension.yml down -v --remove-orphans
docker compose -f docker-compose.e2e.yml up -d --build --wait postgres api web
docker compose -f docker-compose.e2e.yml ps
docker compose -f docker-compose.e2e.yml exec -T api python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"
docker compose -f docker-compose.e2e.yml run --rm --build e2e pnpm test:e2e
docker compose -f docker-compose.e2e.yml down -v --remove-orphans
```

通过 `chrome://extensions` 或 `edge://extensions` 开启开发者模式，加载同一个 `browser-extension` 目录。只在本地 fixture 中明确选择会话后点击扩展读取；草稿必须人工预览、审核、二次确认，最终只能产生 `SEND_BLOCKED_NOT_CONFIGURED`，不得出现凭据输入、网络请求、自动点击或 `SENT`/`DELIVERED`。
测试覆盖领域状态机、金额、归属、幂等、知识阈值、过期知识、Prompt Injection、人工接管、自动分派、双坐席受理冲突、实时队列身份与事件契约、客户与坐席双向消息、运营工单筛选、实时告警与确认幂等、人工工单自动质检、客户满意度归属与单次提交、客户结果回传、内部备注隔离、SLA、API 契约、结构化事件和刷新恢复。Playwright 覆盖客户、坐席实时收单、双向工单沟通、双坐席归属、运营筛选与 CSV 导出、运营主动告警确认与刷新恢复、客服处理方案、客户满意度、自动质检、知识运营与质量看板，以及 9B-1 闲鱼本地连接的显式同意、固定页面 A/B、刷新恢复、失败关闭、标签页隔离、后台登出清除和退出清除；9B-2 领域测试覆盖最近 20 条、稳定排序、未读/置顶/静音、空列表、未知字段、分页截断、页面变化、身份不明、会话失效、重复读取、失败不覆盖成功缓存和 A/B 隔离，Playwright 覆盖手动刷新与刷新恢复；9B-3 领域测试覆盖文本/系统/未知消息、乱序、重复与冲突、空历史、50 条截断、失效、页面变化、旧连接重放、跨账号和伪造会话，Playwright 覆盖点击详情、刷新恢复、无写请求/无写入口及 A/B 切换清除；9B-4 后端测试覆盖 7/30/180/365 天边界、消息/工单子记录/模型与工具审计跨客户清理、安全审计匿名化、失效会话即时删除、幂等运行和诊断/备份不落在线表；正式 Docker 环境使用 PostgreSQL/pgvector。

手动执行保留期限清理（`--as-of` 用于可复现验收，必须带时区）：

```powershell
python -m serviceops.cli purge-retention --as-of 2026-09-05T12:00:00Z
```

命令输出 `policy_version`、所有 cutoff、删除/匿名化计数和 `run_id`。任务不接收客户或账号筛选条件；同一时钟重复运行不会重复删除。完整输入输出示例和非开发者步骤见 [9B-4：账号切换、删除和保留期限](docs/9B-4-账号切换删除和保留期限.md)。

知识检索另有一组可重复的中文口语化评测，覆盖全部 12 个政策条款，每个条款至少 2 条可回答样本，并包含 6 条知识库外拒答样本：

```bash
docker compose exec -T api python -m serviceops.cli evaluate-knowledge
```

评测门禁要求可回答问题条款命中率不低于 95%，知识库外问题误答率为 0。当前固定评测集为 24/24 条款命中、6/6 正确拒答；CLI 以 JSON 输出详细指标和失败样本，未通过时返回非零退出码。

### 阶段 0：知识检索基线冻结

阶段 0 将当前检索明确冻结为 `lexical_v1`，基线数据集为 `knowledge-baseline-30-v1`，评测时钟为 `2026-09-06T00:00:00+00:00`。除保留原有命中率和拒答门禁外，CLI JSON 还输出 `hit_at_1`、`hit_at_3`、`hit_at_5`、`mrr`、`refusal_accuracy` 和 `p95_latency_ms`；Top-5 只用于离线评测，线上默认返回结构仍为 Top-1。

使用以下容器命令同时查看固定 30 条基线和单独记录的同义词、错别字、多意图、冲突及知识库外 exploratory 缺口：

```bash
docker compose exec -T api python -m serviceops.cli evaluate-knowledge --include-exploratory
```

阶段 0 不启用 embedding、RRF、重排、HyDE、文档摄取或外部模型请求。固定基线的输入、输出、信任边界、风险假设、未决项和 Docker-only 验收见 [阶段 0：冻结基线与决策](docs/阶段0-冻结基线与决策.md)。网页入口 <http://localhost:3000/staff/knowledge> 只展示现有条款版本；阶段 0 的机器指标以容器 CLI JSON 为准，不通过网页按钮修改基线或触发外部请求。

### 阶段 1：模块边界、Agent 发布与上下文治理

阶段 1 固定 `AgentRelease`、客户工具能力矩阵和上下文治理策略，并为模型运行审计绑定 Agent/Prompt/工具/知识/评测/上下文版本。治理状态不含 Prompt 正文、消息正文或任何凭据，可在 Docker 容器中查看：

```bash
docker compose exec -T api python -m serviceops.cli agent-governance
```

运营角色可读取同一份只读 JSON：`GET http://localhost:8000/api/ops/agent-governance`。客户和客服会话没有权限。上下文预算、来源/截断/敏感字段失败关闭、输入输出示例、回滚和完整 Docker-only 验收见 [阶段 1：模块边界、Agent 发布与上下文治理](docs/阶段1-模块边界、Agent发布与上下文治理.md)。阶段 1 不实现文档摄取、结构化切块、embedding、向量召回或 RRF。

### 阶段 2：文档摄取、结构化切块与知识快照

阶段 2 把知识运营人员明确提供的本地 Markdown/TXT、PDF 或 DOCX 字节解析为带来源、页码、标题路径、偏移和哈希的结构化切块，再通过评测、审核、发布和回滚形成不可变知识快照。来源 URI 只接受 `file://`、`fixture://`、`kb://` 或 `upload://`；系统不会根据 URI 下载文件，不保存原始文件，也不会改变现有 `KnowledgeArticle` 或 `lexical_v1` 检索行为。单文件上限为 5 MiB，切块上限为 1200 个字符。

容器内可用无密 CLI 查看和操作阶段 2 状态：

```bash
docker compose exec -T api python -m serviceops.cli knowledge-documents
docker compose exec -T api python -m serviceops.cli knowledge-preview --document-id <document-id>
docker compose exec -T api python -m serviceops.cli knowledge-releases
```

知识运营 API 为 `POST/GET /api/ops/knowledge/documents*` 和 `POST/GET /api/ops/knowledge/releases*`，必须使用 `KNOWLEDGE_MANAGER` 后台身份；客户和客服角色拒绝访问。完整输入输出、幂等/重复文件、失败关闭、快照状态流、Docker-only 命令和网页验收步骤见 [阶段 2：文档摄取、结构化切块与知识快照](docs/阶段2-文档摄取、结构化切块与知识快照.md)。阶段 2 不实现 embedding、向量召回、RRF 或外部文件/模型请求。

### 阶段 3：真实 embedding 与混合检索

阶段 3 为显式创建的 `vector_v1`/`hybrid_rrf_v1` 快照生成 1536 维、L2 规范化 embedding，并在 PostgreSQL/pgvector 中执行向量候选和 RRF 融合。默认 `EMBEDDING_PROVIDER=not_configured`，没有服务端 API key 时不伪称 provider 可用；development/test 可显式使用离线 `fixture` provider，production 禁止 fixture。已审核快照必须先完成 embedding 批次，维度、模型、规范化版本或内容哈希不一致时失败关闭。

Stage 3 查询入口为知识运营专用 `POST /api/ops/knowledge/search`，必须明确 `tenant_scope`，并由服务端先过滤渠道、产品和生效期。provider 故障时仅在 `local-demo` 通配范围安全回退到既有 `lexical_v1`，不改变客服 Agent 默认词法行为；跨租户/未授权范围返回空结果。Docker-only embedding、vector/hybrid 输入输出、缓存/重试/成本、网页验收和失败判定见 [阶段 3：真实 embedding 与混合检索](docs/阶段3-真实Embedding与混合检索.md)；容器契约测试使用 `docker-compose.stage3.yml` 与独立测试镜像，不把生产 API 镜像当作测试镜像。阶段 3 不实现 reranker、检索 Trace、质量运营或 HyDE。

### 阶段 4：重排、检索追踪与质量运营

阶段 4 在保持 `lexical_v1`、`vector_v1` 和 `hybrid_rrf_v1` 兼容的前提下提供可选离线 `fixture` 重排、脱敏检索 Trace、候选 rank/score/最终决策、失败回退和质量运营反馈。默认 `RERANKER_PROVIDER=not_configured`；真实重排 provider 尚未配置，不发起网络请求。Trace 只保存查询哈希/长度、受控来源 URI、版本绑定、过滤摘要、候选分数、延迟和错误原因，不保存原始查询、候选正文、凭据或模型 key。

知识运营可通过 `POST /api/ops/knowledge/search` 的 `reranker=fixture` 选择离线重排，通过 `GET /api/ops/knowledge/traces/{trace_id}` 查看解释，通过 `POST /api/ops/knowledge/traces/{trace_id}/feedback` 提交脱敏反馈，并由 `POST /api/ops/knowledge/feedback/{feedback_id}/review` 人工审核；只有 `APPROVED` 反馈进入离线评测候选，不会自动更新生产知识。质量汇总入口为 `GET /api/ops/knowledge/quality`，CLI 为：

```bash
docker compose -f docker-compose.yml -f docker-compose.stage3.yml run --rm api-test python -m serviceops.cli knowledge-quality --window-hours 24
```

阶段 4 的 Docker-only 测试、输入输出、网页验收和失败判定见 [阶段 4：重排、检索追踪与质量运营](docs/阶段4-重排、检索追踪与质量运营.md)。Docker Engine 不可用或容器测试非零时，不能以宿主机 SQLite 结果替代；阶段 4 不实现阶段 5 的查询改写、HyDE 或 multi-query。

### 阶段 5：受控查询增强实验

阶段 5 只对已经由阶段 4 质量证据证明存在的召回缺口做离线/影子实验，提供独立且默认关闭的 `rewrite_v1`、`hyde_v1` 和 `multi_query_v1` 策略。control 始终先执行，treatment 复用同一租户、渠道、产品和有效期过滤；增强失败、拒答安全下降、实体漂移、延迟或成本超预算时回到原始查询。`lexical_v1`、`vector_v1` 和 `hybrid_rrf_v1` 的生产行为不改变，`promotion_allowed` 永远为 `false`。

当前只有 development/test 的确定性离线 `fixture` provider，默认 `QUERY_ENHANCEMENT_PROVIDER=not_configured`、`QUERY_ENHANCEMENT_ENABLED=false`；不保存原始查询，只返回哈希/长度和脱敏候选摘要，不调用外部模型、闲鱼或隐藏接口。知识运营入口为 `POST /api/ops/knowledge/search-experiment` 和 `POST /api/ops/knowledge/query-enhancement/evaluate`，两者均要求 `KNOWLEDGE_MANAGER`，客户和客服角色不能访问。容器 CLI 为 `knowledge-search-experiment` 与 `knowledge-enhancement-evaluate`。

阶段 5 的 Docker-only 测试、固定评测集、输入输出、自动停止门禁、网页/可见验收和失败判定见 [阶段 5：受控查询增强实验](docs/阶段5-受控查询增强实验.md)。Docker Engine 不可用或容器测试非零时，不能用宿主机结果冒充 Docker 证据；阶段 5 不实现阶段 6 的生产发布与持续治理。

### 阶段 6：生产发布与持续治理

阶段 6 增加平台无关的生产发布候选门禁：发布清单绑定应用镜像不可变摘要、数据库迁移 head、AgentRelease、模型策略/提供方/模型版本、KnowledgeRelease、检索策略、评测报告摘要、SBOM 摘要和回滚目标；门禁同时检查签名/SBOM、迁移 dry-run、隔离备份恢复、回滚演练、知识范围、跨版本一致性、保留策略和四方审批。默认状态为 `NOT_CONFIGURED`，完整证据最高只能得到 `READY_FOR_PRODUCTION_REVIEW`，不会自动部署、切流、创建外部资源或发送告警。

阶段 6 固定阻断阶段 5 查询增强晋级、外部平台写入、跨范围泄漏、过期知识命中、Prompt Injection 权限改变、无证据业务承诺和自动退款。`GET /api/ops/production/governance` 读取默认安全状态，`POST /api/ops/production/release-gate` 接收去标识化候选证据；CLI 为 `production-governance` 和 `production-release-gate`。机器字段固定返回 `publish_allowed=false`、`external_requests_enabled=false`；响应仅含版本/摘要、门禁、SLI 比率、维护计数、审批缺口和安全错误码，不含镜像正文、SBOM、Secret、客户数据或模型输入输出。

阶段 6 的 Docker-only 测试、输入输出、Hit@1/3/5、MRR、p95、零结果率、拒答率、引用点击率、一次解决率、人工接管、满意度、单位会话成本、过期知识/孤立切块/失败 embedding/跨版本检查、网页/可见验收和回滚失败判定见 [阶段 6：生产发布与持续治理](docs/阶段6-生产发布与持续治理.md)。Docker Engine 不可用、容器测试非零或任一发布/安全/恢复证据缺失时，不能以宿主机结果宣称生产就绪。

### 阶段 7：生产安全基线与发布工具

阶段 7 将生产配置与开发演示运行时做硬隔离：`APP_ENV=production` 必须关闭演示身份、演示种子、演示重置、API 文档和敏感 tracing，使用非演示 PostgreSQL 与正式 HTTPS Origin；Origin 不接受通配符、本机地址、用户信息、路径、查询串或片段。API 固定返回禁止缓存、禁止嵌入、禁止 MIME 猜测、禁用摄像头/麦克风/定位等安全响应头，CORS 只允许契约内的方法和请求头。

阶段 7 的 `scripts/start-product.cmd`、`scripts/verify.cmd` 和 `scripts/verify-release.cmd` 统一编排 Docker/Compose；后端、仓库契约、前端 lint/build、Playwright、迁移 head、知识评测、确定性 Agent 评测和 HTTP 健康检查都在容器内完成。真实模型烟雾与 70 条评测只有在用户显式配置并选择开关时才运行。详细输入输出、失败判定和 Docker-only 操作见 [阶段 7：生产安全基线与发布工具](docs/阶段7-生产安全基线与发布工具.md)。

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

- 订单、物流和支付仍使用本地模拟数据。淘宝、小红书、闲鱼已具备统一只读协议、12 项官方适配器准入门禁和失败关闭桩，默认状态为 `NOT_CONFIGURED`、不会调用真实平台或产生真实资金动作；9B-1 的闲鱼连接、9B-2 的聊天列表、9B-3 的会话详情、9B-5 的人工审批回复工作流和 9B-6 的 Chrome/Edge 用户控制桥接也仅是本地固定页面模拟，不代表平台授权或官方接入；当前不读取真实页面、不自动发送消息、不下载附件、不执行商品或订单操作。9B-5/9B-6 的发送意图永远不是发送成功，用户必须在官方前台手动粘贴和发送。9C 正式适配器仍等待官方资质、授权协议、接口文档和沙箱账号。
- 默认确定性运行器用于离线演示与稳定测试；DeepSeek 模型模式需要服务端 API Key。仓库永远不包含真实密钥；首次在一台电脑上部署时，需要在本机输入 Key 并完成受控联网验收。
- MVP 使用小型知识集和轻量的中文概念/关键词混合召回；阶段 3 已提供显式知识运营触发的真实 embedding/pgvector 与 `hybrid_rrf_v1` 管道，但默认 provider 仍为 `not_configured`，客服 Agent 继续绑定可回滚的 `lexical_v1`。没有服务端 provider 配置、Docker PostgreSQL/pgvector 证据或人工审核时，不得把离线 fixture 结果描述为生产语义检索。
- 当前已实现开发账号登录、会话过期/吊销和基础角色隔离；尚未接入企业 SSO、客服组织数据范围和排班。生产客户身份计划通过淘宝、小红书、闲鱼等平台的官方授权接口建立映射，不使用页面抓取或让模型决定客户归属。
- 当前运营看板支持单实例内的实时主动告警，尚未接入短信、邮件、企业 IM 等外部通知渠道或长期数据仓库。
- 9B-4 的本地实现不持久化原始解析失败材料、诊断快照或物理数据库备份，因此不会宣称已经完成备份删除传播；真实脱敏诊断、滚动备份和恢复后删除验证属于后续基础设施阶段。
- 阶段 10 的外部工单写入、webhook 和退款沙箱尚未配置；当前仅有 `NOT_CONFIGURED`/`NOT_APPROVED`/`READY_FOR_SANDBOX` 本地门禁，永不启用外部请求。阶段 11 的托管基础设施、外部告警和灾备尚未配置；当前仅有 `NOT_CONFIGURED`/`NOT_APPROVED`/`READY_FOR_PRODUCTION_REVIEW` 本地门禁，永不创建外部资源。阶段 12 当前仅有 `NOT_CONFIGURED`/`NOT_APPROVED`/`READY_FOR_PILOT_REVIEW` 本地门禁，真实模型发布、试点流量和退款执行保持关闭。现有本地状态机、离线评测和模型验证脚本不等于生产就绪。
- 当前质检使用透明的固定规则，不包含模型对语气、同理心或复杂方案合理性的主观判断。
- 当前客户满意度为每个已解决工单一次 1–5 星评价，不包含追评、修改评价或独立问卷编排。
- 暂不包含多渠道、多 Agent、消息队列或 Elasticsearch。

后续生产认证、真实业务适配器、基础设施、灾备和试点发布的实施顺序见 [生产化开发流程](docs/企业客服与工单执行Agent_生产化开发流程_v1.0.md)。
身份与电商平台边界见 [ADR-0001：开发账号认证与多电商平台身份接入](docs/ADR-0001-开发账号认证与多电商平台身份接入.md)。
平台 DTO、错误语义、合同测试范围和正式适配器准入清单见 [电商平台只读适配器契约](docs/电商平台只读适配器契约.md)。
9C 本地准入门禁、输入输出示例、外部阻塞和验收步骤见 [9C：官方只读沙箱适配器准入门禁](docs/9C-官方只读沙箱适配器准入门禁.md)。
阶段 10 本地写入门禁、输入输出示例、外部阻塞和验收步骤见 [阶段 10：真实工单写入与退款沙箱准入门禁](docs/阶段10-真实工单写入与退款沙箱准入门禁.md)。
阶段 11 本地基础设施门禁、输入输出示例、外部阻塞和验收步骤见 [阶段 11：生产基础设施、可观测性与灾备准入门禁](docs/阶段11-生产基础设施可观测性与灾备准入门禁.md)。
阶段 12 本地模型发布与试点门禁、输入输出示例、外部阻塞和验收步骤见 [阶段 12：真实模型发布门禁与小范围试点](docs/阶段12-真实模型发布门禁与小范围试点.md)。
9B-5 本地人工审批回复草稿、撤回、发送意图、失败关闭和固定页面验收见 [9B-5：人工审批回复草稿与发送意图](docs/9B-5-人工审批回复草稿与发送意图.md)。
9B-6 Chrome/Edge Manifest V3 用户控制桥接、扩展契约、Docker 验收、手工加载和失败判定见 [9B-6：Chrome/Edge 用户控制浏览器桥接](docs/9B-6-Chrome-Edge用户控制浏览器桥接.md)。
阶段 12 契约测试覆盖默认未配置、70/69 条评测边界、安全/回退计数、请求和流量开关失败关闭、角色/租户/连接/账号/会话/标签页隔离、候选评审幂等和零模型请求。
