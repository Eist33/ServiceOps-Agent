import { defineConfig } from '@playwright/test';

const isWindows = process.platform === 'win32';
const python = isWindows ? '..\\..\\.venv\\Scripts\\python.exe' : 'python';
const vinext = isWindows
  ? 'node_modules\\.bin\\vinext.cmd'
  : 'node_modules/.bin/vinext';

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://127.0.0.1:3000',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  webServer: [
    {
      command: `${python} -m uvicorn serviceops.main:app --host 127.0.0.1 --port 8000`,
      cwd: '../apps/api',
      url: 'http://127.0.0.1:8000/health',
      reuseExistingServer: true,
      env: {
        DATABASE_URL: 'sqlite:///./e2e.db',
        AGENT_MODE: 'deterministic',
        WEB_ORIGIN: 'http://127.0.0.1:3000',
      },
    },
    {
      command: `${vinext} dev --host 127.0.0.1 --port 3000`,
      cwd: '.',
      url: 'http://127.0.0.1:3000',
      reuseExistingServer: true,
      env: { NEXT_PUBLIC_API_URL: 'http://127.0.0.1:8000' },
    },
  ],
});
