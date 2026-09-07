import { expect, test, type Page } from '@playwright/test';

const API_BASE_URL =
  process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8100';

async function sendNaturalLanguage(page: Page, content: string) {
  await page.getByLabel('输入售后问题').fill(content);
  await page.getByRole('button', { name: '发送消息' }).click();
}

async function loginCustomer(page: Page, name = '林沐') {
  await expect(page.getByRole('heading', { name: '登录客户服务' })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(name) }).click();
  await page.getByLabel('开发环境密码').fill('serviceops');
  await page.getByRole('button', { name: '登录客户服务' }).click();
}

async function selectCustomerConversation(page: Page, conversationId: string) {
  await page.evaluate((selectedConversationId) => {
    const rawSession = sessionStorage.getItem('harbor-support-customer-auth');
    if (!rawSession) throw new Error('Customer authentication session is missing');
    const session = JSON.parse(rawSession) as {
      principal: { principal_id: string };
    };
    localStorage.setItem(
      `harbor-support-conversation:${session.principal.principal_id}`,
      selectedConversationId,
    );
  }, conversationId);
}

async function loginStaff(page: Page, name: '沈清禾' | '陆川' | '许知夏', route: string) {
  await page.goto(route);
  await page.evaluate(() => sessionStorage.removeItem('harbor-support-staff-auth'));
  await page.reload();
  await expect(page.getByRole('heading', { name: '登录客服后台' })).toBeVisible();
  await page.getByRole('button', { name: new RegExp(name) }).click();
  await page.getByLabel('开发环境密码').fill('serviceops');
  await page.getByRole('button', { name: '登录客服后台' }).click();
}

test.beforeEach(async ({ page, request }) => {
  await request.post(`${API_BASE_URL}/api/demo/reset`, {
    headers: { 'X-Demo-Session': 'demo-linmu-session' },
  });
  await page.addInitScript(() => {
    type RegisteredTool = {
      name: string;
      inputSchema: Record<string, unknown>;
      annotations: Record<string, unknown>;
      execute: (input: unknown) => Promise<Record<string, unknown>>;
    };
    const scope = window as Window & {
      __webMcpTools?: Record<string, RegisteredTool>;
    };
    Object.defineProperty(document, 'modelContext', {
      configurable: true,
      value: {
        registerTool(tool: RegisteredTool) {
          scope.__webMcpTools ??= {};
          scope.__webMcpTools[tool.name] = tool;
        },
      },
    });
  });
  await page.goto('/');
  await loginCustomer(page);
  await expect(
    page.getByRole('heading', { name: '售后服务助手', exact: true }),
  ).toBeVisible();
  await expect(page.getByText('正在连接业务服务…')).toBeHidden();
});

test('政策问答展示知识来源与工具证据', async ({ page }) => {
  await sendNaturalLanguage(page, '我收到商品后发现不合适，多少天内可以退货？');
  await expect(page.getByText(/已调用 search_knowledge_base/)).toBeVisible();
  await expect(page.getByText(/来源：平台退换货规则 2026-07/)).toBeVisible();
});

test('订单物流由工具返回确定性异常', async ({ page }) => {
  await sendNaturalLanguage(page, '订单 ORD-20260828-1042 的快递到哪里了？');
  await expect(page.getByText('已收到，我会先核实相关信息。')).toBeVisible();
  await expect(page.getByText('正在分析并准备查询。')).toBeVisible();
  await expect(page.getByText(/已调用 get_order/)).toBeVisible();
  await expect(page.getByText(/已调用 get_shipping_status/)).toBeVisible();
  await expect(page.getByText(/系统规则判定为运输停滞/)).toBeVisible();
});

test('工具失败显示安全失败进度而不伪造成功', async ({ page }) => {
  await sendNaturalLanguage(page, '订单 ORD-999999-0000 的快递到哪里了？');
  await expect(page.getByText(/调用未完成 get_order/)).toBeVisible();
  await expect(
    page.getByText('当前请求未能完成，已安全停止处理；请稍后重试或转人工客服。'),
  ).toBeVisible();
  await expect(page.getByText(/已调用 get_shipping_status/)).toHaveCount(0);
});

test('自然语言触发最近三笔订单选择并在刷新后恢复活动订单', async ({
  page,
}) => {
  await page.getByLabel('输入售后问题').fill('帮我查一下快递');
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(page.getByText('请选择需要处理的订单')).toBeVisible();
  await expect(page.getByText('仅展示当前模拟客户最近 3 笔订单')).toBeVisible();

  await page.getByRole('button', { name: /城市通勤双肩包/ }).click();
  const businessContext = page.getByRole('complementary').last();
  await expect(businessContext.getByText('当前订单')).toBeVisible();
  await expect(businessContext.getByText('ORD-20260828-1042')).toBeVisible();

  await page.reload();
  await expect(page.getByText('正在连接业务服务…')).toBeHidden();
  await expect(businessContext.getByText('ORD-20260828-1042')).toBeVisible();
  await page.getByLabel('输入售后问题').fill('这个订单现在到哪里了？');
  await page.getByRole('button', { name: '发送消息' }).click();
  await expect(page.getByText(/已调用 get_shipping_status/)).toBeVisible();
});

test('新会话创建独立物流工单', async ({ page }) => {
  await sendNaturalLanguage(
    page,
    '订单 ORD-20260828-1042 的物流一直没动，帮我催一下。',
  );
  await expect(page.getByText(/已调用 create_ticket/)).toBeVisible();
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await expect(page.getByText(/TK-/).last()).toBeVisible();
  const businessContext = page.getByRole('complementary').last();
  const firstTicketNumber = (await businessContext.textContent())?.match(
    /TK-\d{8}-[A-Z0-9]{6}/,
  )?.[0];
  expect(firstTicketNumber).toBeTruthy();

  await page.getByRole('button', { name: '新对话' }).click();
  await sendNaturalLanguage(
    page,
    '订单 ORD-20260828-1042 的物流一直没动，帮我催一下。',
  );
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await expect(businessContext.getByText(/TK-/)).toBeVisible();
  await expect(businessContext.getByText('处理中')).toBeVisible();
  await expect
    .poll(async () => {
      const nextNumber = (await businessContext.textContent())?.match(
        /TK-\d{8}-[A-Z0-9]{6}/,
      )?.[0];
      return Boolean(nextNumber && nextNumber !== firstTicketNumber);
    })
    .toBe(true);
  const secondTicketNumber = (await businessContext.textContent())?.match(
    /TK-\d{8}-[A-Z0-9]{6}/,
  )?.[0];
  expect(secondTicketNumber).toBeTruthy();
  expect(secondTicketNumber).not.toBe(firstTicketNumber);
});

test('工单可转人工并展示自动分派与 SLA', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await sendNaturalLanguage(
    page,
    '订单 ORD-20260828-1042 的物流一直没动，帮我催一下。',
  );
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await page.getByRole('button', { name: '查看工单详情' }).click();
  await expect(page.getByText('SLA 状态')).toBeVisible();
  await page.getByRole('button', { name: '转人工处理' }).click();
  await expect(page.getByText('人工接管已建立')).toBeVisible();
  await expect(page.getByText('物流专员组').first()).toBeVisible();
  await page.getByRole('button', { name: '撤销人工接管' }).click();
  await expect(page.getByText(/已撤销人工接管/)).toBeVisible();
  await expect(page.getByText('人工接管已建立')).toBeHidden();
  await expect(page.getByText('尚未转人工')).toBeVisible();
  await expect(page.getByRole('button', { name: '转人工处理' })).toBeEnabled();
});

test('人工坐席可受理、记录并解决工单', async ({ page, request, context }) => {
  const customerHeaders = { 'X-Demo-Session': 'demo-linmu-session' };
  const conversationResponse = await request.post(
    `${API_BASE_URL}/api/conversations`,
    { headers: customerHeaders },
  );
  const conversation = await conversationResponse.json();
  const ticketResponse = await request.post(
    `${API_BASE_URL}/api/tickets`,
    {
      headers: customerHeaders,
      data: {
        conversation_id: conversation.id,
        order_number: 'ORD-20260828-1042',
        ticket_type: 'SHIPPING',
        reason: '物流停滞，需要人工联系承运商',
      },
    },
  );
  const ticket = await ticketResponse.json();
  await selectCustomerConversation(page, conversation.id);
  await request.post(
    `${API_BASE_URL}/api/tickets/${ticket.id}/handoff`,
    { headers: customerHeaders },
  );

  await loginStaff(page, '沈清禾', '/staff/agent');
  await expect(page.getByRole('heading', { name: '人工工单队列' })).toBeVisible();
  await expect(page.getByText(ticket.ticket_number).first()).toBeVisible();
  await page.getByRole('button', { name: '受理此工单' }).click();
  await expect(page.getByText(/已受理工单/)).toBeVisible();
  await expect(page.getByText('沈清禾').first()).toBeVisible();

  const otherAgentPage = await context.newPage();
  await loginStaff(otherAgentPage, '陆川', '/staff/agent');
  await expect(otherAgentPage.getByText('已由 沈清禾 受理')).toBeVisible();
  await expect(otherAgentPage.getByLabel('处理记录或解决说明')).toBeHidden();
  await otherAgentPage.close();

  await expect(page.getByText('由我处理')).toBeVisible();

  await page.getByLabel('回复客户').fill('已联系承运商，正在核查转运进度。');
  await page.getByRole('button', { name: '发送给客户' }).click();
  await expect(page.getByText('回复已发送给客户')).toBeVisible();

  const note = page.getByLabel('处理记录或解决说明');
  await note.fill('已联系承运商，确认今晚恢复转运。');
  await page.getByRole('button', { name: '添加处理记录' }).click();
  await expect(page.getByText('已联系承运商，确认今晚恢复转运。')).toBeVisible();
  await expect(page.getByText('处理记录已保存')).toBeVisible();

  await note.fill('承运商已恢复转运，客户接受继续等待。');
  await page.getByRole('button', { name: '标记已解决' }).click();
  await expect(page.getByText(/已解决/).first()).toBeVisible();
  await expect(page.getByText('工单已完成')).toBeVisible();

  await page.goto('/');
  await expect(page.getByText('客服处理结果')).toBeVisible();
  await expect(
    page.getByText('承运商已恢复转运，客户接受继续等待。'),
  ).toBeVisible();
  await page.getByRole('button', { name: '查看工单详情' }).click();
  await expect(page.getByText('客服处理方案')).toBeVisible();
  await expect(page.getByText('处理人')).toBeVisible();
  await expect(page.getByText('沈清禾').last()).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() => {
        const scope = window as Window & {
          __webMcpTools?: Record<string, unknown>;
        };
        return Boolean(scope.__webMcpTools?.submit_customer_satisfaction_feedback);
      }),
    )
    .toBe(true);
  const contract = await page.evaluate(() => {
    const scope = window as Window & {
      __webMcpTools?: Record<
        string,
        { inputSchema: Record<string, unknown>; annotations: Record<string, unknown> }
      >;
    };
    const tool = scope.__webMcpTools?.submit_customer_satisfaction_feedback;
    return tool
      ? { inputSchema: tool.inputSchema, annotations: tool.annotations }
      : null;
  });
  expect(contract).toMatchObject({
    inputSchema: { required: ['rating'], additionalProperties: false },
    annotations: { readOnlyHint: false, untrustedContentHint: false },
  });
  await expect(
    page.evaluate(async () => {
      const scope = window as Window & {
        __webMcpTools?: Record<
          string,
          { execute: (input: unknown) => Promise<Record<string, unknown>> }
        >;
      };
      await scope.__webMcpTools?.submit_customer_satisfaction_feedback.execute({
        rating: 0,
      });
    }),
  ).rejects.toThrow(/1 至 5/);
  const feedbackResult = await page.evaluate(async () => {
    const scope = window as Window & {
      __webMcpTools?: Record<
        string,
        { execute: (input: unknown) => Promise<Record<string, unknown>> }
      >;
    };
    return scope.__webMcpTools?.submit_customer_satisfaction_feedback.execute({
      rating: 5,
      comment: '回复及时，处理方案清楚。',
    });
  });
  expect(feedbackResult).toMatchObject({ rating: 5, status: 'submitted' });
  await expect(page.getByText('感谢你的评价')).toBeVisible();
  await expect(page.getByText('已提交 5 星评价')).toBeVisible();

  await loginStaff(page, '许知夏', '/staff/operations');
  await expect(page.getByText('人工工单自动质检', { exact: true })).toBeVisible();
  await expect(page.getByText('已质检 1')).toBeVisible();
  await expect(page.getByText('平均 100 分')).toBeVisible();
  await expect(page.getByText('客户评价 1 · 均分 5.0')).toBeVisible();
  await expect(page.getByText('100 分', { exact: true })).toBeVisible();
  await expect(page.getByText('5 星', { exact: true })).toBeVisible();
  await expect(page.getByText('回复及时，处理方案清楚。')).toBeVisible();
  await expect(page.getByText('全部通过')).toBeVisible();
});

test('人工坐席无需刷新即可接收新工单', async ({ page, request }) => {
  const customerHeaders = { 'X-Demo-Session': 'demo-linmu-session' };

  await loginStaff(page, '沈清禾', '/staff/agent');
  await expect(page.getByLabel('实时队列状态')).toContainText('实时已连接');
  await expect(page.getByText('当前筛选下没有工单。')).toBeVisible();

  const conversationResponse = await request.post(
    `${API_BASE_URL}/api/conversations`,
    { headers: customerHeaders },
  );
  const conversation = await conversationResponse.json();
  const ticketResponse = await request.post(
    `${API_BASE_URL}/api/tickets`,
    {
      headers: customerHeaders,
      data: {
        conversation_id: conversation.id,
        order_number: 'ORD-20260828-1042',
        ticket_type: 'SHIPPING',
        reason: '物流停滞，需要人工联系承运商',
      },
    },
  );
  const ticket = await ticketResponse.json();
  await request.post(
    `${API_BASE_URL}/api/tickets/${ticket.id}/handoff`,
    { headers: customerHeaders },
  );

  await expect(page.getByText(ticket.ticket_number).first()).toBeVisible({
    timeout: 7000,
  });
  await expect(
    page.getByLabel('待受理').getByText('1', { exact: true }),
  ).toBeVisible();
  await expect(page.getByLabel('实时队列状态')).toContainText('实时已连接');
});

test('客户与受理坐席可双向同步工单消息', async ({ page, request, context }) => {
  const customerHeaders = { 'X-Demo-Session': 'demo-linmu-session' };
  const conversationResponse = await request.post(
    `${API_BASE_URL}/api/conversations`,
    { headers: customerHeaders },
  );
  const conversation = await conversationResponse.json();
  const ticketResponse = await request.post(
    `${API_BASE_URL}/api/tickets`,
    {
      headers: customerHeaders,
      data: {
        conversation_id: conversation.id,
        order_number: 'ORD-20260828-1042',
        ticket_type: 'SHIPPING',
        reason: '物流停滞，需要人工联系承运商',
      },
    },
  );
  const ticket = await ticketResponse.json();
  await request.post(
    `${API_BASE_URL}/api/tickets/${ticket.id}/handoff`,
    { headers: customerHeaders },
  );

  await selectCustomerConversation(page, conversation.id);
  await page.reload();
  await expect(page.getByText(ticket.ticket_number).last()).toBeVisible();
  await page.getByRole('button', { name: '查看工单详情' }).click();

  const agentPage = await context.newPage();
  await loginStaff(agentPage, '沈清禾', '/staff/agent');
  await expect(agentPage.getByText(ticket.ticket_number).first()).toBeVisible();
  await agentPage.getByRole('button', { name: '受理此工单' }).click();
  await expect(agentPage.getByLabel('回复客户')).toBeVisible();

  await page.getByLabel('发给客服的消息').fill('包裹今晚能恢复转运吗？');
  await page.getByRole('button', { name: '发送给客服' }).click();
  await expect(
    agentPage
      .getByLabel('工单沟通记录')
      .getByText('包裹今晚能恢复转运吗？'),
  ).toBeVisible({ timeout: 7000 });

  await agentPage
    .getByLabel('回复客户')
    .fill('已联系承运商，预计今晚恢复转运。');
  await agentPage.getByRole('button', { name: '发送给客户' }).click();
  await expect(
    page
      .getByLabel('工单沟通记录')
      .getByText('已联系承运商，预计今晚恢复转运。'),
  ).toBeVisible({ timeout: 7000 });
});

test('退款先经客服网页人工审批，再由客户网页明确确认后执行', async ({
  page,
  context,
}) => {
  await sendNaturalLanguage(
    page,
    '订单 ORD-20260828-1042 的物流一直没动，帮我催一下。',
  );
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await page.getByRole('button', { name: '查看工单详情' }).click();
  await page.getByRole('button', { name: '转人工处理' }).click();
  await expect(page.getByText('人工接管已建立')).toBeVisible();
  await page.getByRole('button', { name: 'Close' }).click();

  const agentPage = await context.newPage();
  await loginStaff(agentPage, '沈清禾', '/staff/agent');
  await expect(agentPage.getByRole('heading', { name: '人工工单队列' })).toBeVisible();
  await agentPage.getByTestId('intent-change-panel').getByLabel('退款意图原因').fill(
    '客户补充提出商品不合适，申请退款',
  );
  await agentPage.getByRole('button', { name: '转为退款意图' }).click();
  await expect(agentPage.getByText(/已创建退款处理事项 RF-/)).toBeVisible();
  await expect(agentPage.getByTestId('refund-approval-queue')).toBeVisible();
  await expect(
    agentPage.getByTestId('refund-approval-queue').getByText('待客服审批'),
  ).toBeVisible();
  await expect(page.getByText('等待客服人工审批')).toBeVisible({
    timeout: 7000,
  });
  await agentPage.getByRole('button', { name: /打开退款申请 RF-/ }).click();
  await expect(agentPage.getByTestId('refund-approval-panel')).toBeVisible();
  await agentPage.getByRole('button', { name: '通过人工审批' }).click();
  await expect(
    agentPage.getByText(/已通过人工审批，等待客户确认/),
  ).toBeVisible();

  await expect(page.getByText('客服已同意退款，请确认退款。')).toBeVisible({
    timeout: 7000,
  });
  await expect(page.getByText('客服已同意退款，请确认')).toBeVisible({
    timeout: 7000,
  });
  const confirmButton = page.getByRole('button', { name: '确认退款' });
  await confirmButton.click();
  await expect(page.getByText(/退款已模拟完成/)).toBeVisible();
  await expect(page.getByText('已退款')).toBeVisible();
});

test('客服网页拒绝退款后不再展示第二次审批动作', async ({ page, context }) => {
  await sendNaturalLanguage(
    page,
    '订单 ORD-20260828-1042 的商品不合适，帮我申请退款。',
  );
  await expect(page.getByText('等待客服人工审批')).toBeVisible();

  const agentPage = await context.newPage();
  await loginStaff(agentPage, '沈清禾', '/staff/agent');
  await expect(agentPage.getByTestId('refund-approval-queue')).toBeVisible();
  await agentPage
    .getByRole('button', { name: /打开退款申请 RF-/ })
    .click();
  await expect(agentPage.getByTestId('refund-approval-panel')).toBeVisible();
  await agentPage
    .getByLabel('拒绝退款原因')
    .fill('凭证不足，暂不满足退款条件');
  await agentPage.getByRole('button', { name: '拒绝退款' }).click();
  await expect(agentPage.getByText(/退款申请 RF-.*已拒绝/)).toBeVisible();
  await expect(
    agentPage.getByRole('button', { name: '通过人工审批' }),
  ).toHaveCount(0);
  await expect(
    agentPage.getByRole('button', { name: '拒绝退款' }),
  ).toHaveCount(0);
  await expect(
    agentPage.getByRole('button', { name: '撤回退款' }),
  ).toHaveCount(0);
  await expect(page.getByText('退款状态：已拒绝')).toBeVisible({
    timeout: 7000,
  });
});

test('客服网页审批后可以撤回退款且撤回后不能重复操作', async ({
  page,
  context,
}) => {
  await sendNaturalLanguage(
    page,
    '订单 ORD-20260828-1042 的商品不合适，帮我申请退款。',
  );
  await expect(page.getByText('等待客服人工审批')).toBeVisible();

  const agentPage = await context.newPage();
  await loginStaff(agentPage, '沈清禾', '/staff/agent');
  await expect(agentPage.getByTestId('refund-approval-queue')).toBeVisible();
  await agentPage
    .getByRole('button', { name: /打开退款申请 RF-/ })
    .click();
  await agentPage.getByTestId('refund-approval-panel').getByRole('button', {
    name: '通过人工审批',
  }).click();
  await expect(
    agentPage.getByText(/已通过人工审批，等待客户确认/),
  ).toBeVisible();
  await agentPage.getByLabel('撤回退款原因').fill('客户改为其他售后方案');
  await agentPage.getByRole('button', { name: '撤回退款' }).click();
  await expect(agentPage.getByText(/退款申请 RF-.*已撤回/)).toBeVisible();
  await expect(
    agentPage.getByRole('button', { name: '通过人工审批' }),
  ).toHaveCount(0);
  await expect(
    agentPage.getByRole('button', { name: '撤回退款' }),
  ).toHaveCount(0);
  await expect(page.getByText('退款状态：已撤回')).toBeVisible({
    timeout: 7000,
  });
});

test('运营人员发布知识新版本并替换当前条款', async ({ page }) => {
  await loginStaff(page, '许知夏', '/staff/knowledge');
  await expect(page.getByRole('heading', { name: '知识条款与版本' })).toBeVisible();
  await expect(page.getByText('12').first()).toBeVisible();

  await page.getByLabel('版本').fill('2026-09');
  await page.getByLabel('条款号').fill('第 2.1 条');
  await page.getByLabel('关键词').fill('退货 无理由 10天 签收');
  await page
    .getByLabel('条款内容')
    .fill('大多数商品支持签收后 10 天内无理由退货，商品与赠品需保持完整。');
  await page.getByLabel('来源地址').fill('kb://after-sales/2026-09/第-2.1-条');
  await page.getByRole('button', { name: '发布并立即生效' }).click();

  await expect(page.getByText(/第 2.1 条 · 2026-09 已发布/)).toBeVisible();
  await expect(page.getByRole('cell', { name: '2026-09' })).toBeVisible();
  await expect(page.getByText('历史版本').first()).toBeVisible();
});

test('客户入口不展示后台导航且客服后台内部可稳定跳转', async ({ page }) => {
  await expect(page.getByRole('link', { name: '客服工作台' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '知识运营' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '运营看板' })).toHaveCount(0);

  await loginStaff(page, '沈清禾', '/staff/agent');
  await expect(page.getByRole('navigation', { name: '客服后台导航' })).toBeVisible();
  await expect(page.getByRole('link', { name: '客服工作台' })).toBeVisible();
  await expect(page.getByRole('link', { name: '知识运营' })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '运营看板' })).toHaveCount(0);

  await page.getByRole('button', { name: '退出客服后台' }).click();
  await loginStaff(page, '许知夏', '/staff/knowledge');
  await expect(page.getByRole('link', { name: '客服工作台' })).toHaveCount(0);
  await page.getByRole('link', { name: '知识运营' }).click();
  await expect(page).toHaveURL(/\/staff\/knowledge$/);
  await expect(page.getByRole('heading', { name: '知识条款与版本' })).toBeVisible();

  await page.getByRole('link', { name: '运营看板' }).click();
  await expect(page).toHaveURL(/\/staff\/operations$/);
  await expect(page.getByRole('heading', { name: '运营质量总览' })).toBeVisible();

  await expect(page.getByRole('link', { name: '客服工作台' })).toHaveCount(0);
});

test('旧后台地址兼容跳转到新的 staff 路由', async ({ page }) => {
  await page.goto('/agent');
  await expect(page).toHaveURL(/\/staff\/agent$/);
  await page.goto('/knowledge');
  await expect(page).toHaveURL(/\/staff\/knowledge$/);
  await page.goto('/operations');
  await expect(page).toHaveURL(/\/staff\/operations$/);
});

test('运营看板汇总真实工单、人工接管与工具质量', async ({ page }) => {
  await page.setViewportSize({ width: 900, height: 800 });
  await sendNaturalLanguage(
    page,
    '订单 ORD-20260828-1042 的物流一直没动，帮我催一下。',
  );
  await expect(page.getByText(/已创建物流异常工单 TK-/)).toBeVisible();
  await page.getByRole('button', { name: '查看工单详情' }).click();
  await page.getByRole('button', { name: '转人工处理' }).click();
  await expect(page.getByText('人工接管已建立')).toBeVisible();

  await loginStaff(page, '许知夏', '/staff/operations');
  await expect(page.getByRole('heading', { name: '运营质量总览' })).toBeVisible();
  const integrations = page.getByLabel('电商平台接入状态');
  await expect(integrations.getByText('淘宝', { exact: true })).toBeVisible();
  await expect(integrations.getByText('小红书', { exact: true })).toBeVisible();
  await expect(integrations.getByText('闲鱼', { exact: true })).toBeVisible();
  await expect(integrations.getByText('外部请求已关闭')).toHaveCount(3);
  await expect(page.getByLabel('活动工单').getByText('1', { exact: true })).toBeVisible();
  await expect(page.getByLabel('人工接管').getByText('1', { exact: true })).toBeVisible();
  await expect(page.getByText('100%')).toBeVisible();
  await expect(page.getByRole('cell', { name: '物流专员组' })).toBeVisible();
});

test('运营人员可筛选处理组与 SLA 并导出当前工单', async ({ page, request }) => {
  const customerHeaders = { 'X-Demo-Session': 'demo-linmu-session' };
  async function createTicket(ticketType: 'SHIPPING' | 'OTHER', reason: string) {
    const conversationResponse = await request.post(
      `${API_BASE_URL}/api/conversations`,
      { headers: customerHeaders },
    );
    const conversation = await conversationResponse.json();
    const response = await request.post(`${API_BASE_URL}/api/tickets`, {
      headers: customerHeaders,
      data: {
        conversation_id: conversation.id,
        order_number: 'ORD-20260828-1042',
        ticket_type: ticketType,
        reason,
      },
    });
    return response.json();
  }

  const shipping = await createTicket('SHIPPING', '物流停滞');
  const other = await createTicket('OTHER', '其他售后问题');
  await loginStaff(page, '许知夏', '/staff/operations');
  await expect(page.getByText(shipping.ticket_number)).toBeVisible();
  await expect(page.getByText(other.ticket_number)).toBeVisible();

  await page.getByLabel('处理组筛选').click();
  await page.getByRole('option', { name: '物流专员组' }).click();
  await expect(page.getByText(shipping.ticket_number)).toBeVisible();
  await expect(page.getByText(other.ticket_number)).toBeHidden();
  await expect(page.getByLabel('筛选结果统计')).toContainText('当前 1 张');

  await page.getByLabel('SLA 状态筛选').click();
  await page.getByRole('option', { name: '已超时' }).click();
  await expect(page.getByText('当前筛选条件下没有工单。')).toBeVisible();
  await page.getByLabel('SLA 状态筛选').click();
  await page.getByRole('option', { name: '全部 SLA' }).click();
  await expect(page.getByText(shipping.ticket_number)).toBeVisible();

  const downloadPromise = page.waitForEvent('download');
  await page.getByRole('button', { name: '导出 CSV' }).click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^harbor-tickets-\d{4}-\d{2}-\d{2}\.csv$/);
  const stream = await download.createReadStream();
  const chunks: Uint8Array[] = [];
  for await (const chunk of stream) chunks.push(chunk as Uint8Array);
  const csv = Buffer.concat(chunks).toString('utf8');
  expect(csv).toContain(shipping.ticket_number);
  expect(csv).toContain('物流专员组');
  expect(csv).not.toContain(other.ticket_number);
});

test('运营看板无需刷新即可接收并关闭主动告警', async ({ page, request }) => {
  const customerHeaders = { 'X-Demo-Session': 'demo-linmu-session' };
  await loginStaff(page, '许知夏', '/staff/operations');
  await expect(page.getByLabel('实时告警状态')).toContainText('实时已连接');
  await expect(page.getByText('当前没有需要运营介入的主动告警。')).toBeVisible();

  const conversationResponse = await request.post(
    `${API_BASE_URL}/api/conversations`,
    { headers: customerHeaders },
  );
  const conversation = await conversationResponse.json();
  const ticketResponse = await request.post(`${API_BASE_URL}/api/tickets`, {
    headers: customerHeaders,
    data: {
      conversation_id: conversation.id,
      order_number: 'ORD-20260828-1042',
      ticket_type: 'SHIPPING',
      reason: '物流停滞，需要人工介入',
    },
  });
  const ticket = await ticketResponse.json();
  await request.post(`${API_BASE_URL}/api/tickets/${ticket.id}/handoff`, {
    headers: customerHeaders,
  });

  const alert = page.locator(`[data-alert-ticket="${ticket.id}"]`);
  await expect(alert).toBeVisible();
  await expect(alert).toContainText('人工工单等待受理');
  await expect(alert).toContainText(ticket.ticket_number);
  await expect(alert).toContainText('物流专员组');
  await expect(page.getByText('待确认 1')).toBeVisible();

  await page.getByRole('button', { name: `确认知悉 ${ticket.ticket_number}` }).click();
  await expect(
    page.getByLabel(`告警确认状态 ${ticket.ticket_number}`),
  ).toContainText('已由 许知夏 确认');
  await expect(page.getByText('待确认 0')).toBeVisible();

  await page.reload();
  await expect(page.getByLabel('实时告警状态')).toContainText('实时已连接');
  const restoredAlert = page.locator(`[data-alert-ticket="${ticket.id}"]`);
  await expect(restoredAlert).toBeVisible();
  await expect(
    page.getByLabel(`告警确认状态 ${ticket.ticket_number}`),
  ).toContainText('已由 许知夏 确认');

  const accepted = await request.post(
    `${API_BASE_URL}/api/agent/tickets/${ticket.id}/accept`,
    { headers: { 'X-Agent-Session': 'demo-support-agent-session' } },
  );
  expect(accepted.ok()).toBeTruthy();
  await expect(restoredAlert).toBeHidden();
  await expect(page.getByText('当前没有需要运营介入的主动告警。')).toBeVisible();
  await expect(page.getByLabel('实时告警状态')).toContainText('实时已连接');
});
