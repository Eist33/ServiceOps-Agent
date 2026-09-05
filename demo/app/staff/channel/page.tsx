import { AuthGate } from '@/components/auth-gate';

import XianyuChannelClient from './channel-client';

export default function StaffChannelPage() {
  return (
    <AuthGate area="staff" allowedRoles={['SUPPORT_AGENT']}>
      <XianyuChannelClient />
    </AuthGate>
  );
}
