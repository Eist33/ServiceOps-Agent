'use client';

// oxlint-disable next/no-html-link-for-pages -- Vinext Docker navigation requires full document requests.

import {
  BookOpenText,
  ChartNoAxesCombined,
  Headphones,
  MonitorCog,
} from 'lucide-react';

import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/utils';

type StaffArea = 'agent' | 'knowledge' | 'operations';

const staffAreas = [
  {
    id: 'agent' as const,
    href: '/staff/agent',
    label: '客服工作台',
    icon: Headphones,
  },
  {
    id: 'knowledge' as const,
    href: '/staff/knowledge',
    label: '知识运营',
    icon: BookOpenText,
  },
  {
    id: 'operations' as const,
    href: '/staff/operations',
    label: '运营看板',
    icon: ChartNoAxesCombined,
  },
];

export function StaffNavigation({ active }: { active: StaffArea }) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      <span className="hidden items-center gap-1.5 rounded-lg bg-slate-100 px-2.5 py-2 text-xs font-semibold text-slate-600 xl:flex">
        <MonitorCog className="size-3.5" /> 客服后台
      </span>
      <nav aria-label="客服后台导航" className="flex flex-wrap items-center gap-1.5">
        {staffAreas.map((area) => (
          <a
            aria-current={active === area.id ? 'page' : undefined}
            className={cn(
              buttonVariants({
                variant: active === area.id ? 'secondary' : 'ghost',
                size: 'sm',
              }),
              'gap-1.5',
            )}
            href={area.href}
            key={area.id}
          >
            <area.icon className="size-4" />
            <span className="hidden sm:inline">{area.label}</span>
          </a>
        ))}
      </nav>
    </div>
  );
}
