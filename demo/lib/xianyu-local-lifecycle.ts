import { clearLocalXianyuChatDetail } from './xianyu-chat-detail.ts';
import { clearLocalXianyuChatList } from './xianyu-chat-list.ts';
import { clearLocalXianyuConnection } from './xianyu-local-session.ts';

/** Clear list/detail page caches while retaining a visible connection state. */
export function clearLocalXianyuPageCaches(): void {
  clearLocalXianyuChatList();
  clearLocalXianyuChatDetail();
}

/** Clear every local artifact owned by the current Xianyu experiment tab. */
export function clearLocalXianyuExperimentData(): void {
  clearLocalXianyuConnection();
  clearLocalXianyuPageCaches();
}
