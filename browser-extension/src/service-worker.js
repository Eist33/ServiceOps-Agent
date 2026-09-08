import {
  ADAPTER_STATE,
  BRIDGE_MODE,
  MESSAGE_TYPES,
  createOpaqueId,
  createRequest,
  parseDraft,
  parseRequest,
  parseVisibleSessionSnapshot,
  parseWorkflowSnapshot,
  sanitizeBridgePayload,
} from './protocol.js';
import {
  approveDraft,
  createDraft,
  recordSendIntent,
  resultSnapshot,
  revokeDraft,
} from './workflow.js';

const STATE_KEY_PREFIX = 'serviceops-xianyu-bridge:tab:';
const PENDING_SOURCE_TAB_KEY = 'serviceops-xianyu-bridge:pending-source-tab';
const WORKBENCH_URL = 'http://localhost:13000/staff/channel';
const LOCAL_WORKBENCH_HOSTS = new Set(['localhost', '127.0.0.1']);
const memoryState = new Map();

function now() {
  return new Date().toISOString();
}

function responseFor(requestId, payload = {}, ok = true) {
  return {
    protocol_version: 1,
    request_id: requestId,
    ok,
    payload,
  };
}

function defaultState(tabId) {
  return {
    schema_version: 1,
    mode: BRIDGE_MODE,
    adapter_state: ADAPTER_STATE,
    external_requests_enabled: false,
    tab_id: tabId,
    tab_ref: createOpaqueId(`bridge-tab-${tabId}`),
    visible_session: null,
    workflow_snapshot: null,
    last_error: null,
  };
}

function stateKey(tabId) {
  return `${STATE_KEY_PREFIX}${tabId}`;
}

function storageArea() {
  return globalThis.chrome?.storage?.session ?? null;
}

function storageGet(key) {
  const area = storageArea();
  if (!area) return Promise.resolve(memoryState.get(key));
  return new Promise((resolve) => {
    try {
      area.get(key, (value) => {
        void chrome.runtime.lastError;
        resolve(value?.[key]);
      });
    } catch {
      resolve(memoryState.get(key));
    }
  });
}

function storageSet(key, value) {
  const area = storageArea();
  if (!area) {
    memoryState.set(key, value);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    try {
      area.set({ [key]: value }, () => {
        void chrome.runtime.lastError;
        resolve();
      });
    } catch {
      memoryState.set(key, value);
      resolve();
    }
  });
}

async function readPendingSourceTab() {
  const value = await storageGet(PENDING_SOURCE_TAB_KEY);
  return Number.isInteger(value) && value >= 0 ? value : null;
}

function trustedExtensionMessage(sender) {
  const runtimeId = chrome.runtime?.id;
  if (!runtimeId || !sender || sender.id !== runtimeId) return false;
  const extensionOrigin = chrome.runtime.getURL('');
  if (!sender.tab) {
    return !sender.url || sender.url.startsWith(extensionOrigin);
  }
  return allowedVisiblePage(sender.url) || allowedWorkbenchPage(sender.url);
}

function parseUrl(value) {
  try {
    return new URL(value);
  } catch {
    return null;
  }
}

function allowedVisiblePage(value) {
  const url = parseUrl(value);
  return Boolean(
    url &&
      !url.username &&
      !url.password &&
      ((url.protocol === 'https:' && url.hostname === 'www.goofish.com') ||
        (url.protocol === 'http:' &&
          LOCAL_WORKBENCH_HOSTS.has(url.hostname) &&
          ['3000', '3100', '4173'].includes(url.port))),
  );
}

function allowedWorkbenchPage(value) {
  const url = parseUrl(value);
  return Boolean(
    url &&
      url.protocol === 'http:' &&
      LOCAL_WORKBENCH_HOSTS.has(url.hostname) &&
      (url.port === '3000' || url.port === '3100' || url.port === '4173'),
  );
}

function callChrome(method, ...args) {
  return new Promise((resolve, reject) => {
    try {
      method(...args, (value) => {
        const error = chrome.runtime.lastError;
        if (error) {
          reject(new Error(error.message));
          return;
        }
        resolve(value);
      });
    } catch (error) {
      reject(error instanceof Error ? error : new Error('浏览器扩展调用失败'));
    }
  });
}

async function activeTab() {
  const tabs = await callChrome(chrome.tabs.query.bind(chrome.tabs), {
    active: true,
    lastFocusedWindow: true,
  });
  return tabs?.[0] ?? null;
}

async function readState(tabId) {
  const state = await storageGet(stateKey(tabId));
  if (
    !state ||
    state.schema_version !== 1 ||
    state.mode !== BRIDGE_MODE ||
    state.adapter_state !== ADAPTER_STATE ||
    state.external_requests_enabled !== false ||
    state.tab_id !== tabId ||
    typeof state.tab_ref !== 'string'
  ) {
    const fresh = defaultState(tabId);
    await writeState(fresh);
    return fresh;
  }
  const visibleSession = state.visible_session
    ? parseVisibleSessionSnapshot(state.visible_session)
    : null;
  const workflowSnapshot = state.workflow_snapshot
    ? parseWorkflowSnapshot(state.workflow_snapshot)
    : null;
  if (state.visible_session && !visibleSession) {
    const fresh = defaultState(tabId);
    await writeState(fresh);
    return fresh;
  }
  return {
    ...state,
    visible_session: visibleSession,
    workflow_snapshot: workflowSnapshot,
  };
}

async function writeState(state) {
  await storageSet(stateKey(state.tab_id), state);
}

async function sendToTab(tabId, message) {
  return callChrome(chrome.tabs.sendMessage.bind(chrome.tabs), tabId, message);
}

async function injectFile(tabId, file) {
  await callChrome(chrome.scripting.executeScript.bind(chrome.scripting), {
    target: { tabId },
    files: [file],
  });
}

async function sendAfterInjection(tabId, message, file) {
  try {
    return await sendToTab(tabId, message);
  } catch {
    await injectFile(tabId, file);
    return sendToTab(tabId, message);
  }
}

function failedPayload(errorCode, errorMessage) {
  return {
    result: 'FAILED',
    mode: BRIDGE_MODE,
    adapter_state: ADAPTER_STATE,
    external_requests_enabled: false,
    error_code: errorCode,
    error_message: errorMessage,
  };
}

async function readCurrentVisibleSession() {
  const tab = await activeTab();
  if (!tab?.id || !allowedVisiblePage(tab.url)) {
    return failedPayload(
      'PAGE_NOT_ALLOWED',
      '当前标签页不是允许的闲鱼官方可见页面；本地桥接不会读取其他页面。',
    );
  }
  const state = await readState(tab.id);
  const message = createRequest(MESSAGE_TYPES.READ_VISIBLE_SESSION, {
    tab_ref: state.tab_ref,
    now: now(),
  });
  let response;
  try {
    response = await sendAfterInjection(tab.id, message, 'src/content-script.js');
  } catch {
    return failedPayload(
      'CONTENT_SCRIPT_UNAVAILABLE',
      '当前页面无法提供受控只读标记，已失败关闭。',
    );
  }
  const snapshot = response?.result === 'SUCCESS'
    ? parseVisibleSessionSnapshot(response.snapshot)
    : null;
  if (!snapshot || snapshot.tab_ref !== state.tab_ref) {
    return response?.result === 'FAILED'
      ? response
      : failedPayload('IDENTITY_UNCONFIRMED', '当前账号、连接或会话无法确认，已失败关闭。');
  }
  const next = {
    ...state,
    visible_session: snapshot,
    workflow_snapshot: null,
    last_error: null,
  };
  await writeState(next);
  return response;
}

async function currentStatePayload() {
  const tab = await activeTab();
  if (!tab?.id) {
    return { state: null, status: 'NOT_CONFIGURED' };
  }
  const state = await readState(tab.id);
  return { state, status: state.adapter_state };
}

async function applyWorkflowAction(message) {
  const tab = await activeTab();
  if (!tab?.id) return { ok: false, error_code: 'TAB_NOT_AVAILABLE' };
  const state = await readState(tab.id);
  const snapshot = state.visible_session;
  let result;
  const payload = message.payload;
  const draft = state.workflow_snapshot?.draft ?? null;
  if (message.type === MESSAGE_TYPES.CREATE_DRAFT) {
    result = createDraft({
      snapshot,
      body: payload.body,
      now: now(),
      ttlMs: payload.ttl_ms,
      draftId: payload.draft_id,
    });
  } else if (message.type === MESSAGE_TYPES.APPROVE_DRAFT) {
    result = approveDraft({
      draft,
      currentSnapshot: snapshot,
      actorRole: payload.actor_role,
      now: now(),
      approvalActionId: payload.approval_action_id,
    });
  } else if (message.type === MESSAGE_TYPES.REVOKE_DRAFT) {
    result = revokeDraft({
      draft,
      currentSnapshot: snapshot,
      actorRole: payload.actor_role,
      now: now(),
      revokeActionId: payload.revoke_action_id,
    });
  } else {
    result = recordSendIntent({
      draft,
      currentSnapshot: snapshot,
      actorRole: payload.actor_role,
      now: now(),
      sendActionId: payload.send_action_id,
      confirmation: payload.confirmation,
    });
  }
  if (result?.draft) {
    const workflowSnapshot = resultSnapshot(
      state.workflow_snapshot,
      snapshot,
      result,
    );
    const next = {
      ...state,
      workflow_snapshot: workflowSnapshot,
      last_error: result.ok ? null : result.error_code,
    };
    await writeState(next);
  }
  return result;
}

async function openWorkbench() {
  const sourceTab = await activeTab();
  if (!sourceTab?.id || !allowedVisiblePage(sourceTab.url)) {
    return {
      opened: false,
      error_code: 'SOURCE_TAB_NOT_SELECTED',
      error_message: '请先在允许的可见页面选择会话，再打开本地工作台。',
    };
  }
  await storageSet(PENDING_SOURCE_TAB_KEY, sourceTab.id);
  const tab = await callChrome(chrome.tabs.create.bind(chrome.tabs), {
    url: WORKBENCH_URL,
    active: true,
  });
  return { opened: Boolean(tab?.id), url: WORKBENCH_URL };
}

async function pushDraftToWorkbench() {
  const tab = await activeTab();
  if (!tab?.id || !allowedWorkbenchPage(tab.url)) {
    return {
      ok: false,
      error_code: 'WORKBENCH_NOT_SELECTED',
      error_message: '请先由您打开本地客服工作台，再点击交给工作台。',
    };
  }
  const sourceTabId = await readPendingSourceTab();
  if (sourceTabId === null || sourceTabId === tab.id) {
    return {
      ok: false,
      error_code: 'SOURCE_TAB_NOT_SELECTED',
      error_message: '没有可交给工作台的已选择来源标签页。',
    };
  }
  const state = await readState(sourceTabId);
  const draft = state.workflow_snapshot?.draft;
  const payload = sanitizeBridgePayload({ draft });
  if (!payload) {
    return {
      ok: false,
      error_code: 'DRAFT_NOT_READY',
      error_message: '当前标签页没有可交给工作台的本地草稿。',
    };
  }
  const message = createRequest(MESSAGE_TYPES.DELIVER_DRAFT_TO_WORKBENCH, payload);
  try {
    const response = await sendAfterInjection(tab.id, message, 'src/workbench-bridge.js');
    return response?.ok
      ? { ok: true, delivered: true }
      : { ok: false, error_code: 'WORKBENCH_REJECTED', error_message: '工作台拒绝了不符合白名单的草稿。' };
  } catch {
    return {
      ok: false,
      error_code: 'WORKBENCH_UNAVAILABLE',
      error_message: '工作台桥接不可用，草稿保持本地且没有发送。',
    };
  }
}

chrome.runtime.onMessage.addListener((rawMessage, sender, sendResponse) => {
  const message = parseRequest(rawMessage);
  if (!message || !trustedExtensionMessage(sender)) {
    sendResponse(responseFor(rawMessage?.request_id ?? 'unknown', {
      error_code: 'MESSAGE_SOURCE_REJECTED',
      error_message: '扩展消息来源无法确认，已失败关闭。',
    }, false));
    return false;
  }

  (async () => {
    try {
      if (message.type === MESSAGE_TYPES.GET_STATE) {
        return responseFor(message.request_id, await currentStatePayload());
      }
      if (message.type === MESSAGE_TYPES.READ_CURRENT_VISIBLE_SESSION) {
        return responseFor(message.request_id, await readCurrentVisibleSession());
      }
      if (
        [
          MESSAGE_TYPES.CREATE_DRAFT,
          MESSAGE_TYPES.APPROVE_DRAFT,
          MESSAGE_TYPES.REVOKE_DRAFT,
          MESSAGE_TYPES.RECORD_SEND_INTENT,
        ].includes(message.type)
      ) {
        const result = await applyWorkflowAction(message);
        return responseFor(message.request_id, result, result?.ok !== false);
      }
      if (message.type === MESSAGE_TYPES.OPEN_WORKBENCH) {
        return responseFor(message.request_id, await openWorkbench());
      }
      if (message.type === MESSAGE_TYPES.PUSH_DRAFT_TO_WORKBENCH) {
        const result = await pushDraftToWorkbench();
        return responseFor(message.request_id, result, result.ok);
      }
      return responseFor(message.request_id, {
        error_code: 'MESSAGE_REJECTED',
        error_message: '该扩展动作未配置。',
      }, false);
    } catch {
      return responseFor(message.request_id, {
        error_code: 'FAILED_CLOSED',
        error_message: '扩展动作出现未知错误，已失败关闭且没有外部操作。',
      }, false);
    }
  })().then(sendResponse);
  return true;
});
