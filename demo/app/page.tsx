import { AuthGate } from '@/components/auth-gate';

import DemoClient from './demo-client';

export default function Home() {
  return (
    <AuthGate area="customer" allowedRoles={["CUSTOMER"]}>
      <DemoClient />
    </AuthGate>
  );
}
