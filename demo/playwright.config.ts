import { defineConfig } from '@playwright/test';
import { tmpdir } from 'node:os';
import { join } from 'node:path';

const isWindows = process.platform === 'win32';
const python = isWindows ? '..\\..\\.venv\\Scripts\\python.exe' : 'python';
const vinext = isWindows
  ? 'node_modules\\.bin\\vinext.cmd'
  : 'node_modules/.bin/vinext';
const apiBaseUrl =
  process.env.E2E_API_BASE_URL ?? 'http://127.0.0.1:8100';
const webBaseUrl =
  process.env.E2E_WEB_BASE_URL ?? 'http://127.0.0.1:3100';
const databasePath = join(tmpdir(), `serviceops-e2e-${process.pid}.db`).replaceAll(
  '\\',
  '/',
);
const manageLocalServers = process.env.E2E_EXTERNAL_SERVER !== 'true';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  // Docker E2E workers share one seeded PostgreSQL demo database.  Serialise
  // reset-and-login flows so one test cannot reset another test's session.
  workers: process.env.E2E_EXTERNAL_SERVER === 'true' ? 1 : undefined,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: webBaseUrl,
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: manageLocalServers
    ? [
        {
          command: `${python} -m uvicorn serviceops.main:app --host 127.0.0.1 --port 8100 --timeout-graceful-shutdown 2`,
          cwd: '../apps/api',
          url: `${apiBaseUrl}/health`,
          reuseExistingServer: !process.env.CI,
          env: {
            DATABASE_URL: `sqlite:///${databasePath}`,
            AGENT_MODE: 'deterministic',
            WEB_ORIGIN: webBaseUrl,
          },
        },
        {
          command: `${vinext} dev --host 127.0.0.1 --port 3100`,
          cwd: '.',
          url: webBaseUrl,
          reuseExistingServer: !process.env.CI,
          env: { NEXT_PUBLIC_API_URL: apiBaseUrl },
        },
      ]
    : undefined,
});
