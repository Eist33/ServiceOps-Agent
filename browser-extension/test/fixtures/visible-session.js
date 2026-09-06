export const NOW = '2026-09-06T10:00:00.000Z';
export const TAB_REF = 'tab-fixture-a';

export function makeFixtureElement(attributes, textContent = '', children = [], visible = true) {
  return {
    textContent,
    getAttribute(name) {
      return Object.hasOwn(attributes, name) ? attributes[name] : null;
    },
    getClientRects() {
      return visible ? [{ width: 1, height: 1 }] : [];
    },
    querySelectorAll(selector) {
      if (selector === '[data-serviceops-xianyu-message="true"]') return children;
      return [];
    },
  };
}

export function makeDocument({
  selected = true,
  connectionRef = 'connection-a',
  accountRef = 'account-a',
  conversationRef = 'conversation-a',
  sourcePageVersion = 'local-fixed-page-v1',
  detailReadAt = NOW,
  messages = [
    makeFixtureElement(
      {
        'data-serviceops-xianyu-message': 'true',
        'data-message-id': 'message-a-1',
        'data-sender': 'OTHER',
        'data-sent-at': NOW,
      },
      '请问什么时候发货？',
    ),
  ],
  rootVisible = true,
} = {}) {
  const root = makeFixtureElement(
    {
      'data-serviceops-xianyu-visible-session': 'true',
      'data-serviceops-xianyu-selected': selected ? 'true' : 'false',
      'data-connection-ref': connectionRef,
      'data-account-ref': accountRef,
      'data-conversation-ref': conversationRef,
      'data-source-page-version': sourcePageVersion,
      'data-detail-read-at': detailReadAt,
    },
    '',
    messages,
    rootVisible,
  );
  return {
    querySelectorAll(selector) {
      if (selector === '[data-serviceops-xianyu-visible-session="true"]') return [root];
      return [];
    },
  };
}
