import { AuthGate } from '@/components/auth-gate';

export default function StaffLayout({ children }: { children: React.ReactNode }) {
  return <AuthGate area="staff">{children}</AuthGate>;
}
