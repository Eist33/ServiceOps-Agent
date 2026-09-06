import { MESSAGE_TYPES, parseRequest, sanitizeBridgePayload } from './protocol.js';

const INJECTED_MARKER = '__SERVICEOPS_XIANYU_BRIDGE_WORKBENCH_V1__';

if (!globalThis[INJECTED_MARKER]) {
  globalThis[INJECTED_MARKER] = true;

  chrome.runtime.onMessage.addListener((rawMessage, _sender, sendResponse) => {
    const message = parseRequest(rawMessage);
    if (!message || message.type !== MESSAGE_TYPES.DELIVER_DRAFT_TO_WORKBENCH) {
      sendResponse({ ok: false, error_code: 'MESSAGE_REJECTED' });
      return false;
    }
    const payload = sanitizeBridgePayload(message.payload);
    if (!payload) {
      sendResponse({ ok: false, error_code: 'PAYLOAD_REJECTED' });
      return false;
    }
    window.postMessage(
      {
        source: 'serviceops-xianyu-bridge',
        ...payload,
      },
      window.location.origin,
    );
    sendResponse({ ok: true });
    return false;
  });
}
