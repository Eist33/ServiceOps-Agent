import { createServer } from 'node:http';

const PORT = Number(process.env.PORT ?? 4173);
const DETAIL_READ_AT = '2026-09-06T00:00:00.000Z';

const fixtureHtml = `<!doctype html>
<html lang="zh-CN">
  <head><meta charset="utf-8"><title>ServiceOps local visible fixture</title></head>
  <body>
    <main
      data-serviceops-xianyu-visible-session="true"
      data-serviceops-xianyu-selected="true"
      data-source-page-version="local-fixed-page-v1"
      data-connection-ref="connection-a"
      data-account-ref="account-a"
      data-conversation-ref="conversation-a"
      data-detail-read-at="${DETAIL_READ_AT}"
    >
      <h1>本地可见会话 fixture</h1>
      <p data-serviceops-xianyu-message="true" data-message-id="message-a-1" data-sender="OTHER" data-sent-at="2026-09-05T23:59:00.000Z">您好，这是一条本地测试消息。</p>
      <p data-serviceops-xianyu-message="true" data-message-id="message-a-2" data-sender="SELF" data-sent-at="2026-09-05T23:59:30.000Z">您好，我会先为您核实。</p>
    </main>
  </body>
</html>`;

const server = createServer((request, response) => {
  const pathname = new URL(request.url ?? '/', 'http://fixture.local').pathname;
  if (pathname === '/health') {
    response.writeHead(200, { 'content-type': 'text/plain; charset=utf-8' });
    response.end('ok');
    return;
  }
  if (pathname === '/' || pathname === '/fixture') {
    response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
    response.end(fixtureHtml);
    return;
  }
  response.writeHead(404, { 'content-type': 'text/plain; charset=utf-8' });
  response.end('not found');
});

server.listen(PORT, '0.0.0.0');
