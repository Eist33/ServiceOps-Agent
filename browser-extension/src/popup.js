import {
  MESSAGE_TYPES,
  createOpaqueId,
  createRequest,
} from './protocol.js';

const elements = {
  status: document.querySelector('#status'),
  notice: document.querySelector('#notice'),
  session: document.querySelector('#session'),
  sessionDetails: document.querySelector('#session-details'),
  draftBody: document.querySelector('#draft-body'),
  draft: document.querySelector('#draft'),
  read: document.querySelector('#read'),
  openWorkbench: document.querySelector('#open-workbench'),
  pushWorkbench: document.querySelector('#push-workbench'),
  createDraft: document.querySelector('#create-draft'),
};

let state = null;
let busy = false;

function send(type, payload = {}) {
  return new Promise((resolve) => {
    chrome.runtime.sendMessage(createRequest(type, payload), (response) => {
      const error = chrome.runtime.lastError;
      resolve(
        error
          ? { ok: false, payload: { error_code: 'EXTENSION_ERROR', error_message: error.message } }
          : response ?? { ok: false, payload: { error_code: 'EMPTY_RESPONSE', error_message: '扩展没有返回结果。' } },
      );
    });
  });
}

function showNotice(message, ok = false) {
  elements.notice.textContent = message ?? '';
  elements.notice.className = ok ? 'notice ok' : 'notice';
}

function short(value) {
  return typeof value === 'string' && value.length > 14
    ? `${value.slice(0, 8)}…${value.slice(-4)}`
    : value ?? '未确认';
}

function detail(label, value) {
  const dt = document.createElement('dt');
  dt.textContent = label;
  const dd = document.createElement('dd');
  dd.textContent = value;
  elements.sessionDetails.append(dt, dd);
}

function renderSession() {
  const session = state?.visible_session;
  elements.sessionDetails.replaceChildren();
  if (!session) {
    elements.session.classList.add('hidden');
    return;
  }
  elements.session.classList.remove('hidden');
  detail('页面状态', `${session.mode} / ${session.adapter_state}`);
  detail('账号引用', short(session.account_ref));
  detail('会话引用', short(session.conversation_ref));
  detail('连接引用', short(session.connection_ref));
  detail('标签页引用', short(session.tab_ref));
  detail('读取消息', `${session.messages.length} 条（只读）`);
}

function renderDraft() {
  const draft = state?.workflow_snapshot?.draft;
  elements.draft.replaceChildren();
  if (!draft) {
    elements.draft.classList.add('hidden');
    elements.createDraft.disabled = false;
    return;
  }
  elements.draft.classList.remove('hidden');
  elements.createDraft.disabled = true;
  const meta = document.createElement('p');
  meta.className = 'draft-meta';
  meta.textContent = `状态：${draft.status} · 有效期至 ${new Date(draft.expires_at).toLocaleString('zh-CN')}`;
  const body = document.createElement('p');
  body.className = 'draft-body';
  body.textContent = draft.body;
  elements.draft.append(meta, body);

  const actions = document.createElement('div');
  actions.className = 'draft-actions';
  if (draft.status === 'DRAFTED') {
    const approve = document.createElement('button');
    approve.textContent = '我已人工预览并审核';
    approve.addEventListener('click', () => runAction(MESSAGE_TYPES.APPROVE_DRAFT, {
      actor_role: 'SUPPORT_AGENT',
      approval_action_id: createOpaqueId('bridge-approval'),
    }));
    actions.append(approve);
  }
  if (draft.status === 'APPROVED') {
    const confirm = document.createElement('label');
    confirm.className = 'confirm';
    const checkbox = document.createElement('input');
    checkbox.type = 'checkbox';
    const text = document.createElement('span');
    text.textContent = '我已再次确认当前账号、会话和正文；下一步仅记录 send-intent，不会发送。';
    confirm.append(checkbox, text);
    const sendIntent = document.createElement('button');
    sendIntent.textContent = '记录本地 send-intent';
    sendIntent.disabled = true;
    checkbox.addEventListener('change', () => {
      sendIntent.disabled = !checkbox.checked;
    });
    sendIntent.addEventListener('click', () => runAction(MESSAGE_TYPES.RECORD_SEND_INTENT, {
      actor_role: 'SUPPORT_AGENT',
      send_action_id: createOpaqueId('bridge-send'),
      confirmation: 'CONFIRM_SEND',
    }));
    actions.append(confirm, sendIntent);
  }
  if (['DRAFTED', 'APPROVED'].includes(draft.status)) {
    const revoke = document.createElement('button');
    revoke.className = 'secondary';
    revoke.textContent = '撤回本地草稿';
    revoke.addEventListener('click', () => runAction(MESSAGE_TYPES.REVOKE_DRAFT, {
      actor_role: 'SUPPORT_AGENT',
      revoke_action_id: createOpaqueId('bridge-revoke'),
    }));
    actions.append(revoke);
  }
  if (draft.status === 'SEND_BLOCKED_NOT_CONFIGURED') {
    const manual = document.createElement('p');
    manual.className = 'muted';
    manual.textContent = '未发送：请回到官方闲鱼可见页面，由您手动粘贴并发送。';
    actions.append(manual);
  }
  const clear = document.createElement('button');
  clear.className = 'secondary';
  clear.textContent = '清除本地草稿';
  clear.addEventListener('click', async () => {
    state = { ...state, workflow_snapshot: null };
    renderDraft();
    showNotice('工作台重开或标签页关闭后，旧草稿不会自动复用。', true);
  });
  actions.append(clear);
  elements.draft.append(actions);
}

function render() {
  elements.status.textContent = `${state?.mode ?? 'USER_CONTROLLED'} / ${state?.adapter_state ?? 'NOT_CONFIGURED'}`;
  renderSession();
  renderDraft();
}

async function refresh() {
  const response = await send(MESSAGE_TYPES.GET_STATE);
  state = response.payload?.state ?? null;
  render();
}

async function runAction(type, payload) {
  if (busy) return;
  busy = true;
  showNotice('处理中…');
  const response = await send(type, payload);
  if (response.payload?.error_message) showNotice(response.payload.error_message);
  else if (response.payload?.error_code === 'NOT_CONFIGURED') showNotice('已记录本地意图，没有发送。', true);
  else showNotice(response.ok ? '本地动作已记录。' : '动作未完成，已失败关闭。', response.ok);
  await refresh();
  busy = false;
}

elements.read.addEventListener('click', async () => {
  if (busy) return;
  busy = true;
  showNotice('只读取您当前明确选择的可见会话…');
  const response = await send(MESSAGE_TYPES.READ_CURRENT_VISIBLE_SESSION);
  if (response.payload?.error_message) showNotice(response.payload.error_message);
  else showNotice('已读取本地白名单会话；未读取其他页面内容。', true);
  await refresh();
  busy = false;
});

elements.createDraft.addEventListener('click', () =>
  runAction(MESSAGE_TYPES.CREATE_DRAFT, {
    body: elements.draftBody.value,
    ttl_ms: 10 * 60 * 1_000,
    draft_id: createOpaqueId('bridge-draft'),
  }),
);

elements.openWorkbench.addEventListener('click', async () => {
  const response = await send(MESSAGE_TYPES.OPEN_WORKBENCH);
  showNotice(
    response.payload?.error_message ??
      (response.ok ? '已打开本地工作台；请在工作台标签页点击“交给已打开的工作台”。' : '工作台未打开。'),
    response.ok,
  );
});

elements.pushWorkbench.addEventListener('click', async () => {
  const response = await send(MESSAGE_TYPES.PUSH_DRAFT_TO_WORKBENCH);
  showNotice(
    response.payload?.error_message ??
      (response.ok ? '已把本地草稿交给工作台预览；仍需人工审核。' : '工作台未接收草稿。'),
    response.ok,
  );
});

void refresh();
