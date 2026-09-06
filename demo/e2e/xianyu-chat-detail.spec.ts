import { expect, test, type Page } from '@playwright/test';

const API_BASE_URL =
  process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8100';
const DETAIL_KEY = 'harbor-support-xianyu-local-chat-detail';

async function loginSupportAgent(page: Page, name = '沈清禾') {
  await page.goto('/staff/channel');
  await page.evaluate(() =>
    sessionStorage.removeItem('harbor-support-staff-auth'),
  );
  await page.reload();
  await expect(
    page.getByRole('heading', { name: '登录客服后台' }),
  ).toBeVisible();
  await page.getByRole('button', { name: new RegExp(name) }).click();
  await page.getByLabel('开发环境密码').fill('serviceops');
  await page.getByRole('button', { name: '登录客服后台' }).click();
  await expect(
    page.getByRole('heading', { name: '闲鱼实验连接' }),
  ).toBeVisible();
}

async function connectAndRefresh(page: Page, fixture: 'A' | 'B' = 'A') {
  await page.getByLabel('同意闲鱼本地实验告知').check();
  await page
    .getByRole('button', { name: `连接本地模拟账号 ${fixture}` })
    .click();
  await expect(page.getByText('已连接（本地）', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: '手动刷新聊天列表' }).click();
  await expect(page.getByText(/已读取 \d+ 个会话/)).toBeVisible();
}

test.beforeEach(async ({ request }) => {
  await request.post(`${API_BASE_URL}/api/demo/reset`, {
    headers: { 'X-Demo-Session': 'demo-linmu-session' },
  });
});

test('点击已确认会话只读取详情，刷新可恢复且没有写操作入口', async ({
  page,
}) => {
  await loginSupportAgent(page);
  await connectAndRefresh(page);

  const writeRequests: string[] = [];
  page.on('request', (request) => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
      writeRequests.push(`${request.method()} ${request.url()}`);
    }
  });

  await page.getByRole('button', { name: '查看聊天会话 晨光手作' }).click();
  const detail = page.getByLabel('闲鱼会话详情只读映射');
  await expect(detail).toBeVisible();
  await expect(detail.getByText('已读取 7 条消息')).toBeVisible();
  await expect(detail.getByText('我方 · TEXT')).toBeVisible();
  await expect(detail.getByText('系统 · SYSTEM')).toBeVisible();
  await expect(detail.getByText('对方 · TEXT')).toBeVisible();
  await expect(detail.getByText('暂不支持的消息类型：图片消息')).toBeVisible();
  await expect(detail.getByText('暂不支持的消息类型：商品卡片')).toBeVisible();
  await expect(detail.getByText('暂不支持的消息类型：订单卡片')).toBeVisible();
  await expect(
    detail.getByText('暂不支持的消息类型', { exact: true }),
  ).toBeVisible();
  await expect(
    detail.getByRole('button', { name: '创建本地回复草稿' }),
  ).toBeVisible();
  await expect(detail.getByRole('link')).toHaveCount(0);

  const stored = await page.evaluate((key) => {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  }, DETAIL_KEY);
  expect(stored).toMatchObject({
    result: 'SUCCESS',
    connection_id: expect.any(String),
    conversation_id: 'a-conv-1001',
    source_page_version: 'local-fixed-page-v1',
    messages: expect.any(Array),
  });
  expect(JSON.stringify(stored)).not.toMatch(
    /手机号|验证码|cookie|token|serviceops|secret/i,
  );

  await page.reload();
  await expect(page.getByText('已读取 7 条消息')).toBeVisible();
  await expect(
    page.getByLabel('消息 a-msg-1003').getByText('尺码可以换吗？', {
      exact: true,
    }),
  ).toBeVisible();
  expect(writeRequests).toEqual([]);
});

test('切换账号会清除详情，旧账号会话不能继续显示或读取', async ({ page }) => {
  await loginSupportAgent(page);
  await connectAndRefresh(page, 'A');
  await page.getByRole('button', { name: '查看聊天会话 晨光手作' }).click();
  await expect(
    page.getByLabel('消息 a-msg-1003').getByText('尺码可以换吗？', {
      exact: true,
    }),
  ).toBeVisible();

  await page.getByRole('button', { name: '退出并清除本地连接' }).click();
  await expect(page.getByText('已退出并清除本地连接数据。')).toBeVisible();
  await connectAndRefresh(page, 'B');

  const detail = page.getByLabel('闲鱼会话详情只读映射');
  await expect(detail).toBeVisible();
  await expect(
    detail.getByText(
      '点击上方聊天列表中的会话，读取当前连接下的最近历史消息。',
    ),
  ).toBeVisible();
  await expect(page.getByText('尺码可以换吗？', { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByRole('button', { name: '查看聊天会话 同名买家' }),
  ).toBeVisible();

  await page.getByRole('button', { name: '查看聊天会话 同名买家' }).click();
  await expect(detail.getByText('想确认发货时间。')).toBeVisible();
  await expect(detail.getByText('当前消息来自本地模拟系统。')).toBeVisible();
  await expect(detail.getByText('暂不支持的消息类型：订单卡片')).toBeVisible();
  await expect(page.getByText('尺码可以换吗？', { exact: true })).toHaveCount(
    0,
  );
});
