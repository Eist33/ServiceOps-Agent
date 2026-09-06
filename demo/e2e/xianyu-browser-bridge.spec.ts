import { expect, test, type Page } from '@playwright/test';

const API_BASE_URL =
  process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8100';
const CONNECTION_KEY = 'harbor-support-xianyu-local-connection';
const DETAIL_KEY = 'harbor-support-xianyu-local-chat-detail';
const TAB_KEY = 'harbor-support-xianyu-local-reply-tab-ref';
const WORKFLOW_KEY = 'harbor-support-xianyu-local-reply-workflow';

type BridgeRefs = {
  connection_ref: string;
  account_ref: string;
  conversation_ref: string;
  source_page_version: string;
  detail_read_at: string;
  tab_ref: string;
};

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

async function initialiseReplyTab(page: Page) {
  const panel = page.getByLabel('本地回复草稿与发送门禁');
  await panel.getByRole('button', { name: '创建本地回复草稿' }).click();
  await expect(panel.getByText('待坐席审核', { exact: true })).toBeVisible();
  await panel.getByRole('button', { name: '取消草稿' }).click();
  await expect(panel.getByText('已取消', { exact: true })).toBeVisible();
  await panel
    .getByRole('button', { name: '清除本地草稿和审计' })
    .click();
}

async function readRefs(page: Page): Promise<BridgeRefs> {
  return page.evaluate(
    ({ connectionKey, detailKey, tabKey }) => {
      const connection = JSON.parse(
        sessionStorage.getItem(connectionKey) ?? 'null',
      ) as { connection_id?: string } | null;
      const detail = JSON.parse(
        sessionStorage.getItem(detailKey) ?? 'null',
      ) as {
        conversation_id?: string;
        source_page_version?: string;
        read_at?: string;
      } | null;
      const tabRef = sessionStorage.getItem(tabKey);
      if (
        !connection?.connection_id ||
        !detail?.conversation_id ||
        !detail.source_page_version ||
        !detail.read_at ||
        !tabRef
      ) {
        throw new Error('local fixture context is incomplete');
      }
      return {
        connection_ref: connection.connection_id,
        account_ref: 'account-a',
        conversation_ref: detail.conversation_id,
        source_page_version: detail.source_page_version,
        detail_read_at: detail.read_at,
        tab_ref: tabRef,
      };
    },
    { connectionKey: CONNECTION_KEY, detailKey: DETAIL_KEY, tabKey: TAB_KEY },
  );
}

function makeBridgeMessage(refs: BridgeRefs, tabRef = refs.tab_ref) {
  const createdAt = new Date().toISOString();
  return {
    protocol_version: 1,
    kind: 'XIANYU_DRAFT_BRIDGE',
    mode: 'USER_CONTROLLED',
    adapter_state: 'NOT_CONFIGURED',
    external_requests_enabled: false,
    draft: {
      schema_version: 1,
      draft_id: 'extension-draft-a',
      mode: 'USER_CONTROLLED',
      adapter_state: 'NOT_CONFIGURED',
      external_requests_enabled: false,
      context: { ...refs, tab_ref: tabRef },
      body: '扩展只提供本地草稿预览，仍需人工核对。',
      created_at: createdAt,
      expires_at: new Date(Date.parse(createdAt) + 600_000).toISOString(),
      status: 'DRAFTED',
      approved_at: null,
      approval_action_id: null,
      revoke_action_id: null,
      send_action_id: null,
      send_requested_at: null,
      failure_code: null,
    },
  };
}

test.beforeEach(async ({ request }) => {
  await request.post(`${API_BASE_URL}/api/demo/reset`, {
    headers: { 'X-Demo-Session': 'demo-linmu-session' },
  });
});

test('同源扩展草稿只显示待导入预览，人工点击后无法确认上下文则失败关闭', async ({
  page,
}) => {
  await loginSupportAgent(page);
  await openSelectedConversation(page);
  await initialiseReplyTab(page);
  const refs = await readRefs(page);
  const writes: string[] = [];
  page.on('request', (request) => {
    if (['POST', 'PUT', 'PATCH', 'DELETE'].includes(request.method())) {
      writes.push(`${request.method()} ${request.url()}`);
    }
  });

  await page.evaluate(
    (message) => window.postMessage(message, window.location.origin),
    makeBridgeMessage(refs),
  );
  const preview = page.getByLabel('浏览器扩展待导入草稿');
  await expect(preview).toBeVisible();
  await expect(
    preview.getByText('扩展只提供本地草稿预览，仍需人工核对。', {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.evaluate((key) => sessionStorage.getItem(key), WORKFLOW_KEY),
  ).resolves.toBeNull();

  await preview
    .getByRole('button', { name: '核对上下文并导入本地草稿' })
    .click();
  await expect(
    page.getByText(
      '扩展草稿的账号、连接、会话、标签页或页面版本不匹配，已失败关闭。',
      { exact: true },
    ),
  ).toBeVisible();
  expect(writes).toEqual([]);
  expect(
    await page.evaluate((key) => sessionStorage.getItem(key), WORKFLOW_KEY),
  ).toBeNull();
});

test('跨标签页扩展草稿只显示预览，导入上下文不匹配时失败关闭', async ({
  page,
}) => {
  await loginSupportAgent(page);
  await openSelectedConversation(page);
  const refs = await page.evaluate(
    ({ connectionKey, detailKey }) => {
      const connection = JSON.parse(
        sessionStorage.getItem(connectionKey) ?? 'null',
      ) as { connection_id?: string } | null;
      const detail = JSON.parse(
        sessionStorage.getItem(detailKey) ?? 'null',
      ) as {
        conversation_id?: string;
        source_page_version?: string;
        read_at?: string;
      } | null;
      if (
        !connection?.connection_id ||
        !detail?.conversation_id ||
        !detail.source_page_version ||
        !detail.read_at
      ) {
        throw new Error('local fixture context is incomplete');
      }
      return {
        connection_ref: connection.connection_id,
        account_ref: 'account-a',
        conversation_ref: detail.conversation_id,
        source_page_version: detail.source_page_version,
        detail_read_at: detail.read_at,
        tab_ref: 'foreign-tab-fixture',
      } satisfies BridgeRefs;
    },
    { connectionKey: CONNECTION_KEY, detailKey: DETAIL_KEY },
  );

  await page.evaluate(
    (message) => window.postMessage(message, window.location.origin),
    makeBridgeMessage(refs),
  );
  const preview = page.getByLabel('浏览器扩展待导入草稿');
  await expect(preview).toBeVisible();
  await preview
    .getByRole('button', { name: '核对上下文并导入本地草稿' })
    .click();
  await expect(
    page.getByText(
      '扩展草稿的账号、连接、会话、标签页或页面版本不匹配，已失败关闭。',
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.evaluate((key) => sessionStorage.getItem(key), WORKFLOW_KEY),
  ).resolves.toBeNull();
});
