import { expect, test, type Page } from '@playwright/test';

const API_BASE_URL = 'http://127.0.0.1:8100';
const CONNECTION_KEY = 'harbor-support-xianyu-local-connection';

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

test.beforeEach(async ({ request }) => {
  await request.post(`${API_BASE_URL}/api/demo/reset`, {
    headers: { 'X-Demo-Session': 'demo-linmu-session' },
  });
});

test('支持坐席可在本地固定页面完成连接、刷新恢复和退出清除', async ({
  page,
}) => {
  await loginSupportAgent(page);

  await expect(page.getByText('未连接', { exact: true })).toBeVisible();
  await expect(page.getByText('当前账号无法确认，停止连接')).toBeVisible();
  await expect(
    page.getByRole('link', { name: '打开官方闲鱼页面' }),
  ).toHaveAttribute('href', 'https://www.goofish.com/');

  await page.getByRole('button', { name: '连接本地模拟账号 A' }).click();
  await expect(page.getByText('请先阅读并同意实验告知')).toBeVisible();
  await page.getByLabel('同意闲鱼本地实验告知').check();
  await page.getByRole('button', { name: '连接本地模拟账号 A' }).click();
  await expect(
    page
      .getByLabel('闲鱼实验连接')
      .getByText('本地模拟账号 A', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('已连接（本地）', { exact: true })).toBeVisible();
  await expect(page.getByText('最后同步时间', { exact: true })).toBeVisible();
  await expect(
    page.getByText('聊天列表（只读实验）', { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: '手动刷新聊天列表' }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: '退出并清除本地连接' }),
  ).toBeVisible();

  await page.getByRole('button', { name: '手动刷新聊天列表' }).click();
  await expect(
    page.getByText('已读取 5 个会话', { exact: false }),
  ).toBeVisible();
  await expect(page.getByText('晨光手作', { exact: true })).toBeVisible();
  await expect(page.getByText('未读：2', { exact: true })).toBeVisible();
  await expect(page.getByText('置顶', { exact: true })).toBeVisible();
  await expect(page.getByText('静音', { exact: true })).toHaveCount(2);
  await expect(page.getByText('UNKNOWN', { exact: true })).toBeVisible();

  const stored = await page.evaluate((key) => {
    const raw = sessionStorage.getItem(key);
    return raw ? JSON.parse(raw) : null;
  }, CONNECTION_KEY);
  expect(stored).toMatchObject({
    provider: 'XIANYU',
    display_identifier: '本地模拟账号 A',
    status: 'CONNECTED',
    source_page_version: 'local-fixed-page-v1',
  });
  expect(JSON.stringify(stored)).not.toMatch(
    /手机号|验证码|cookie|token|serviceops/i,
  );

  await page.reload();
  await expect(
    page
      .getByLabel('闲鱼实验连接')
      .getByText('本地模拟账号 A', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('已连接（本地）', { exact: true })).toBeVisible();
  await expect(
    page.getByText('已读取 5 个会话', { exact: false }),
  ).toBeVisible();
  await expect(page.getByText('晨光手作', { exact: true })).toBeVisible();

  await page.getByRole('button', { name: '页面/身份不确定' }).click();
  await expect(page.getByText('需要重新登录', { exact: true })).toBeVisible();
  await expect(page.getByText('已失败关闭，不能继续读取')).toBeVisible();
  await expect(page.getByRole('button', { name: '重新登录' })).toBeVisible();

  await page.getByRole('button', { name: '重新登录' }).click();
  await expect(page.getByText('旧连接已清除')).toBeVisible();
  await page.getByLabel('同意闲鱼本地实验告知').check();
  await page.getByRole('button', { name: '连接本地模拟账号 B' }).click();
  await expect(
    page
      .getByLabel('闲鱼实验连接')
      .getByText('本地模拟账号 B', { exact: true }),
  ).toBeVisible();
  await expect(page.getByText('尚未读取当前页面的聊天列表')).toBeVisible();
  await page.getByRole('button', { name: '手动刷新聊天列表' }).click();
  await expect(
    page.getByText('已读取 3 个会话', { exact: false }),
  ).toBeVisible();
  await expect(page.getByText('远山来信', { exact: true })).toBeVisible();
  await expect(page.getByText('晨光手作', { exact: true })).toHaveCount(0);
  await expect(page.getByText('本地模拟账号 A', { exact: true })).toHaveCount(
    0,
  );

  await page.getByRole('button', { name: '退出并清除本地连接' }).click();
  await expect(page.getByText('已退出并清除本地连接数据。')).toBeVisible();
  await expect(page.getByText('未连接', { exact: true })).toBeVisible();
  await expect(
    page.evaluate((key) => sessionStorage.getItem(key), CONNECTION_KEY),
  ).resolves.toBeNull();
});

test('闲鱼实验连接仅对支持坐席可见', async ({ page }) => {
  await page.goto('/staff/channel');
  await page.evaluate(() =>
    sessionStorage.removeItem('harbor-support-staff-auth'),
  );
  await page.reload();
  await expect(
    page.getByRole('heading', { name: '登录客服后台' }),
  ).toBeVisible();
  await page.getByRole('button', { name: /许知夏/ }).click();
  await page.getByLabel('开发环境密码').fill('serviceops');
  await page.getByRole('button', { name: '登录客服后台' }).click();

  await expect(
    page.getByRole('heading', { name: '当前账号无权访问' }),
  ).toBeVisible();
  await expect(page.getByText('闲鱼实验连接', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('link', { name: '渠道账号' })).toHaveCount(0);
});

test('后台登出和重新登录会清除旧的本地连接', async ({ page }) => {
  await loginSupportAgent(page, '沈清禾');
  await page.getByLabel('同意闲鱼本地实验告知').check();
  await page.getByRole('button', { name: '连接本地模拟账号 A' }).click();
  await expect(
    page
      .getByLabel('闲鱼实验连接')
      .getByText('本地模拟账号 A', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '手动刷新聊天列表' }).click();
  await expect(
    page.getByText('已读取 5 个会话', { exact: false }),
  ).toBeVisible();

  await page.getByRole('button', { name: '退出客服后台' }).click();
  await expect(
    page.getByRole('heading', { name: '登录客服后台' }),
  ).toBeVisible();

  await page.getByRole('button', { name: /陆川/ }).click();
  await page.getByLabel('开发环境密码').fill('serviceops');
  await page.getByRole('button', { name: '登录客服后台' }).click();
  await expect(
    page.getByRole('heading', { name: '闲鱼实验连接' }),
  ).toBeVisible();
  await expect(page.getByText('未连接', { exact: true })).toBeVisible();
  await expect(page.getByText('本地模拟账号 A', { exact: true })).toHaveCount(
    0,
  );
  await expect(
    page.getByText('聊天列表（只读实验）', { exact: true }),
  ).toHaveCount(0);
});

test('本地连接仅存在当前浏览器标签页', async ({ context, page }) => {
  await loginSupportAgent(page);
  await page.getByLabel('同意闲鱼本地实验告知').check();
  await page.getByRole('button', { name: '连接本地模拟账号 A' }).click();
  await expect(
    page
      .getByLabel('闲鱼实验连接')
      .getByText('本地模拟账号 A', { exact: true }),
  ).toBeVisible();
  await page.getByRole('button', { name: '手动刷新聊天列表' }).click();
  await expect(
    page.getByText('已读取 5 个会话', { exact: false }),
  ).toBeVisible();

  const otherTab = await context.newPage();
  try {
    await loginSupportAgent(otherTab, '陆川');
    await expect(otherTab.getByText('未连接', { exact: true })).toBeVisible();
    await expect(
      otherTab.getByText('本地模拟账号 A', { exact: true }),
    ).toHaveCount(0);
  } finally {
    await otherTab.close();
  }
});
