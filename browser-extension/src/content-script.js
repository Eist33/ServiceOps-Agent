/*
 * Deliberately self-contained because chrome.scripting injects this file into
 * the current tab as a classic script. It is only installed after an
 * explicit popup action and never reads the page until a READ_VISIBLE_SESSION
 * message arrives from this extension.
 */
(function installVisibleSessionReader() {
  const MARKER = '__SERVICEOPS_XIANYU_BRIDGE_CONTENT_V1__';
  if (globalThis[MARKER]) return;
  globalThis[MARKER] = true;

  const SENSITIVE = /(验证码|短信验证码|password|passwd|cookie|token|access[_-]?token|authorization|bearer)/i;
  const ID = /^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$/;
  const PAGE_VERSION = 'local-fixed-page-v1';

  function failure(errorCode, errorMessage) {
    return {
      protocol_version: 1,
      result: 'FAILED',
      mode: 'USER_CONTROLLED',
      adapter_state: 'NOT_CONFIGURED',
      external_requests_enabled: false,
      error_code: errorCode,
      error_message: errorMessage,
    };
  }

  function iso(value) {
    return typeof value === 'string' && Number.isFinite(Date.parse(value));
  }

  function identifier(value) {
    return typeof value === 'string' && ID.test(value);
  }

  function safeText(value) {
    return (
      typeof value === 'string' &&
      value.length <= 2_000 &&
      !SENSITIVE.test(value)
    );
  }

  function visible(element) {
    return (
      element &&
      typeof element.getClientRects === 'function' &&
      element.getClientRects().length > 0
    );
  }

  function attribute(element, name) {
    const value = element.getAttribute(name);
    return typeof value === 'string' ? value.trim() : '';
  }

  function readVisibleSession(message) {
    const payload = message.payload;
    const tabRef = payload?.tab_ref;
    const currentTime = payload?.now;
    if (!identifier(tabRef) || !iso(currentTime)) {
      return failure('INVALID_INPUT', '当前标签页绑定或时间无效。');
    }

    const roots = document.querySelectorAll(
      '[data-serviceops-xianyu-visible-session="true"]',
    );
    if (roots.length !== 1 || !visible(roots[0])) {
      return failure(
        'PAGE_NOT_CONFIGURED',
        '当前可见页面没有受控只读标记，已失败关闭。',
      );
    }
    const root = roots[0];
    if (attribute(root, 'data-serviceops-xianyu-selected') !== 'true') {
      return failure(
        'SESSION_NOT_SELECTED',
        '请先在当前可见页面明确选择一个会话。',
      );
    }

    const connectionRef = attribute(root, 'data-connection-ref');
    const accountRef = attribute(root, 'data-account-ref');
    const conversationRef = attribute(root, 'data-conversation-ref');
    const detailReadAt =
      attribute(root, 'data-detail-read-at') || currentTime;
    if (
      attribute(root, 'data-source-page-version') !== PAGE_VERSION ||
      !identifier(connectionRef) ||
      !identifier(accountRef) ||
      !identifier(conversationRef) ||
      !iso(detailReadAt) ||
      Date.parse(detailReadAt) > Date.parse(currentTime)
    ) {
      return failure(
        'IDENTITY_UNCONFIRMED',
        '当前账号、连接、会话或页面版本无法确认。',
      );
    }

    const nodes = Array.from(
      root.querySelectorAll('[data-serviceops-xianyu-message="true"]'),
    );
    if (nodes.length > 50) {
      return failure('MESSAGE_LIMIT', '当前页面消息数量超过本地上限。');
    }
    const messages = nodes.map((node) => ({
      message_id: attribute(node, 'data-message-id'),
      sender: attribute(node, 'data-sender') || 'UNKNOWN',
      text: (node.textContent || '').trim(),
      sent_at: attribute(node, 'data-sent-at') || null,
    }));
    if (
      messages.some(
        (item) =>
          !identifier(item.message_id) ||
          !['SELF', 'OTHER', 'SYSTEM', 'UNKNOWN'].includes(item.sender) ||
          !safeText(item.text) ||
          (item.sent_at !== null &&
            (!iso(item.sent_at) ||
              Date.parse(item.sent_at) > Date.parse(currentTime))),
      )
    ) {
      return failure('MESSAGE_INVALID', '当前可见会话消息字段无法确认。');
    }

    return {
      protocol_version: 1,
      result: 'SUCCESS',
      mode: 'USER_CONTROLLED',
      adapter_state: 'NOT_CONFIGURED',
      external_requests_enabled: false,
      snapshot: {
        schema_version: 1,
        mode: 'USER_CONTROLLED',
        adapter_state: 'NOT_CONFIGURED',
        provider: 'XIANYU',
        external_requests_enabled: false,
        tab_ref: tabRef,
        connection_ref: connectionRef,
        account_ref: accountRef,
        conversation_ref: conversationRef,
        source_page_version: PAGE_VERSION,
        selected_at: currentTime,
        detail_read_at: detailReadAt,
        messages,
      },
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (
      !message ||
      message.protocol_version !== 1 ||
      message.type !== 'READ_VISIBLE_SESSION' ||
      typeof message.request_id !== 'string' ||
      !message.payload ||
      typeof message.payload !== 'object'
    ) {
      sendResponse(
        failure('MESSAGE_REJECTED', '扩展消息不符合本地白名单。'),
      );
      return false;
    }
    sendResponse(readVisibleSession(message));
    return false;
  });
})();
