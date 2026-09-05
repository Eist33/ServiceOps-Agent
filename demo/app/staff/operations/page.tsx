import { AuthGate } from '@/components/auth-gate';

import OperationsClient from '../../operations/operations-client';

export default function StaffOperationsPage() {
  return (
    <AuthGate area="staff" allowedRoles={["KNOWLEDGE_MANAGER", "OPERATIONS_MANAGER"]}>
      <OperationsClient />
    </AuthGate>
  );
}
