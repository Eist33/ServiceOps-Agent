import { expect, test, type Page } from '@playwright/test';

const API_BASE_URL = 'http://127.0.0.1:8100';
const WORKFLOW_KEY = 'harbor-support-xianyu-local-reply-workflow';

async function loginSupportAgent(page: Page) {
  await page.goto('/staff/channel');
  await page.evaluate(() =>
    sessionStorage.removeItem('harbor-support-staff-auth'),
  );
  await page.reload();
  await expect(
    page.getByRole('heading', { name: '登录客服后台' }),
  ).toBeVisible();
  await page.getByRole('button', { name: /沈清禾/ }).click();
  await page.getByLabel('开发环境密码').fill('serviceops');
  await page.getByRole('button', { name: '登录客服后台' }).click();
  await expect(
    page.getByRole('heading', { name: '闲鱼实验连接' }),
  ).toBeVisible();
}

async function openSelectedConversation(page: Page) {
  await page.getByLabel('同意闲鱼本地实验告知').check();
  await page.getByRole('button', { name: '连接本地模拟账号 A' }).click();
  await page.getByRole('button', { name: '手动刷新聊天列表' }).click();
  await page.getByRole('button', { name: '查看聊天会话 晨光手作' }).click();
  await expect(page.getByLabel('闲鱼会话详情只读映射')).toBeVisible();
}

test.beforeEach(async ({ request }) => {
  await request.post(`${API_BASE_URL}/api/demo/reset`, {
    headers: { 'X-Demo-Session': 'demo-linmu-session' },
  });
});

test('选中当前会话后只能生成本地草稿，经两次人工确认后记录发送意图', async ({
  page,
}) => {
  await loginSupportAgent(page);
  await openSelectedConversation(page);

  const outboundWrites: string[] = [];
  page.on('request', (request) => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
      outboundWrites.push(`${request.method()} ${request.url()}`);
    }
  });

  const panel = page.getByLabel('本地回复草稿与发送门禁');
  await panel
    .getByLabel('回复草稿内容')
    .fill('您好，已看到您的消息，我会先为您核实。');
  await panel.getByRole('button', { name: '创建本地回复草稿' }).click();
  await expect(panel.getByText('待坐席审核', { exact: true })).toBeVisible();
  await expect(
    panel.getByText('您好，已看到您的消息，我会先为您核实。'),
  ).toBeVisible();

  await panel.getByRole('button', { name: '我已审核，进入发送确认' }).click();
  await expect(
    panel.getByText('已审核，待最终确认', { exact: true }),
  ).toBeVisible();
  const sendIntent = panel.getByRole('button', {
    name: '记录发送意图（需最终确认）',
  });
  await expect(sendIntent).toBeDisabled();

  await panel.getByLabel('我已再次确认发送内容和当前会话').check();
  await expect(sendIntent).toBeEnabled();
  await sendIntent.click();

  await expect(panel.getByText('发送已阻断', { exact: true })).toBeVisible();
  await expect(
    panel.getByText('未发送：真实平台适配器未配置', { exact: true }),
  ).toBeVisible();
  await expect(
    panel.getByText(/只记录了一个本地发送请求，没有网络请求/),
  ).toBeVisible();
  expect(outboundWrites).toEqual([]);

  const stored = await page.evaluate((key) => {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  }, WORKFLOW_KEY);
  expect(stored).toMatchObject({
    schema_version: 1,
    draft: {
      status: 'SEND_BLOCKED_NOT_CONFIGURED',
      failure_code: 'NOT_CONFIGURED',
      send_action_id: expect.any(String),
    },
  });
  expect(JSON.stringify(stored)).not.toMatch(
    /手机号|验证码|cookie|token|secret|goofish\.com/i,
  );
});

test('已审核草稿可以在发送意图前撤回，撤回后不能继续发送', async ({ page }) => {
  await loginSupportAgent(page);
  await openSelectedConversation(page);

  const panel = page.getByLabel('本地回复草稿与发送门禁');
  await panel.getByRole('button', { name: '创建本地回复草稿' }).click();
  await panel.getByRole('button', { name: '我已审核，进入发送确认' }).click();
  await panel.getByRole('button', { name: '取消草稿' }).click();
  await expect(panel.getByText('已取消', { exact: true })).toBeVisible();
  await expect(
    panel.getByText('草稿已由坐席取消，不会进入发送请求。', { exact: true }),
  ).toBeVisible();
});
