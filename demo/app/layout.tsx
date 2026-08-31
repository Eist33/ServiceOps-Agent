import type { Metadata } from 'next';

import './globals.css';

export const metadata: Metadata = {
  title: 'Harbor Support · 企业客服 Agent Demo',
  description: '电商售后客服与工单执行 Agent 交互原型',
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
