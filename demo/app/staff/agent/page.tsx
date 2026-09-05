import { AuthGate } from '@/components/auth-gate';

import AgentWorkbenchClient from '../../agent/workbench-client';

export default function StaffAgentPage() {
  return (
    <AuthGate area="staff" allowedRoles={["SUPPORT_AGENT"]}>
      <AgentWorkbenchClient />
    </AuthGate>
  );
}
