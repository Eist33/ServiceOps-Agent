import { AuthGate } from '@/components/auth-gate';

import KnowledgeClient from '../../knowledge/knowledge-client';

export default function StaffKnowledgePage() {
  return (
    <AuthGate area="staff" allowedRoles={["KNOWLEDGE_MANAGER"]}>
      <KnowledgeClient />
    </AuthGate>
  );
}
