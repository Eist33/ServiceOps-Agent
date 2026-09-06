import {
  ADAPTER_STATE,
  BRIDGE_MODE,
  LOCAL_VISIBLE_PAGE_VERSION,
  makeVisibleSessionSnapshot,
  parseVisibleSessionSnapshot,
} from './protocol.js';

const ROOT_SELECTOR = '[data-serviceops-xianyu-visible-session="true"]';
const MESSAGE_SELECTOR = '[data-serviceops-xianyu-message="true"]';

function failure(errorCode, errorMessage) {
  return {
    protocol_version: 1,
    result: 'FAILED',
    mode: BRIDGE_MODE,
    adapter_state: ADAPTER_STATE,
    external_requests_enabled: false,
    error_code: errorCode,
    error_message: errorMessage,
  };
}
function isVisible(element) {
  return (
    element &&
    typeof element.getClientRects === 'function' &&
    element.getClientRects().length > 0
  );
}

function readAttribute(element, name) {
  const value = element.getAttribute(name);
  return typeof value === 'string' ? value.trim() : '';
}

function isPastOrPresentIsoDate(value, now) {
  const parsed = Date.parse(value);
  return Number.isFinite(parsed) && parsed <= Date.parse(now);
}

/**
 * Read only the explicitly selected, visible fixture contract.  The real
 * Xianyu page does not expose these data attributes, so a real page returns a
 * deterministic failure without returning HTML, cookies, account labels, or
 * page-wide text.
 */
export function readVisibleSessionFromDocument(documentRef, { tabRef, now }) {
  if (
    typeof tabRef !== 'string' ||
    tabRef.trim().length === 0 ||
    typeof now !== 'string' ||
    !Number.isFinite(Date.parse(now))
  ) {
    return failure('INVALID_INPUT', '当前标签页绑定或时间无效。');
  }

  const roots = documentRef.querySelectorAll(ROOT_SELECTOR);
  if (roots.length !== 1 || !isVisible(roots[0])) {
    return failure(
      'PAGE_NOT_CONFIGURED',
      '当前可见页面没有可验证的闲鱼只读标记，已失败关闭。',
    );
  }
  const root = roots[0];
  if (readAttribute(root, 'data-serviceops-xianyu-selected') !== 'true') {
    return failure(
      'SESSION_NOT_SELECTED',
      '请先在当前可见页面明确选择一个会话，再点击扩展读取。',
    );
  }

  const sourcePageVersion = readAttribute(root, 'data-source-page-version');
  const connectionRef = readAttribute(root, 'data-connection-ref');
  const accountRef = readAttribute(root, 'data-account-ref');
  const conversationRef = readAttribute(root, 'data-conversation-ref');
  const detailReadAt = readAttribute(root, 'data-detail-read-at') || now;
  if (
    sourcePageVersion !== LOCAL_VISIBLE_PAGE_VERSION ||
    !connectionRef ||
    !accountRef ||
    !conversationRef ||
    !isPastOrPresentIsoDate(detailReadAt, now)
  ) {
    return failure(
      'IDENTITY_UNCONFIRMED',
      '当前账号、连接、会话或页面版本无法确认，已失败关闭。',
    );
  }

  const messages = Array.from(root.querySelectorAll(MESSAGE_SELECTOR));
  if (messages.length > 50) {
    return failure('MESSAGE_LIMIT', '当前页面消息数量超过本地读取上限。');
  }
  const mappedMessages = messages.map((message) => ({
    message_id: readAttribute(message, 'data-message-id'),
    sender: readAttribute(message, 'data-sender') || 'UNKNOWN',
    text: (message.textContent ?? '').trim(),
    sent_at: readAttribute(message, 'data-sent-at') || null,
  }));
  if (
    mappedMessages.some(
      (message) =>
        !message.message_id ||
        !message.text ||
        (message.sent_at !== null && !isPastOrPresentIsoDate(message.sent_at, now)),
    )
  ) {
    return failure(
      'MESSAGE_INVALID',
      '当前可见会话消息字段无法确认，未返回消息内容。',
    );
  }

  const snapshot = makeVisibleSessionSnapshot({
    tabRef,
    connectionRef,
    accountRef,
    conversationRef,
    selectedAt: now,
    detailReadAt,
    messages: mappedMessages,
  });
  if (!snapshot || !parseVisibleSessionSnapshot(snapshot)) {
    return failure(
      'IDENTITY_UNCONFIRMED',
      '当前可见会话不符合本地白名单结构，已失败关闭。',
    );
  }
  return {
    protocol_version: 1,
    result: 'SUCCESS',
    mode: BRIDGE_MODE,
    adapter_state: ADAPTER_STATE,
    external_requests_enabled: false,
    snapshot,
  };
}
