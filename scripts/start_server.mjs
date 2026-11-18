import { spawn } from 'node:child_process';
import { existsSync } from 'node:fs';
import { resolve } from 'node:path';
import { buildUvicornArgs, ensurePythonEnv, resolveListenConfig } from './python_env.mjs';

process.on('uncaughtException', (err) => {
  console.error('[SpendSense] Uncaught startup exception:', err?.stack || err?.message || err);
  process.exit(1);
});

process.on('unhandledRejection', (reason) => {
  console.error('[SpendSense] Unhandled startup rejection:', reason);
  process.exit(1);
});

try {
  const root = process.cwd();
  const entryFile = resolve(root, 'app', 'main.py');
  if (!existsSync(entryFile)) {
    throw new Error(`Missing application entrypoint at ${entryFile} (cwd=${root})`);
  }

  const geminiKey = (process.env.GEMINI_API_KEY || '').trim();
  if (!geminiKey || geminiKey === 'MY_GEMINI_API_KEY' || geminiKey === 'changeme' || geminiKey === 'none') {
    console.warn('[SpendSense] GEMINI_API_KEY is not set; starting with offline AI fallbacks enabled.');
  }

  const pyBin = ensurePythonEnv(root, { fast: true });
  const { host, port } = resolveListenConfig(process.env);
  const uvicornArgs = buildUvicornArgs(process.env);

  console.log(`[SpendSense] Starting server on ${host}:${port} using ${pyBin}...`);

  const child = spawn(pyBin, uvicornArgs, {
    stdio: 'inherit',
    cwd: root,
    env: process.env,
  });

  child.on('error', (err) => {
    console.error('[SpendSense] Failed to spawn uvicorn process:', err?.stack || err?.message || err);
    process.exit(1);
  });

  const forwardSignal = (signal) => {
    try {
      if (!child.killed) child.kill(signal);
    } catch (err) {
      console.error(`[SpendSense] Error forwarding ${signal}:`, err);
    }
  };

  process.on('SIGTERM', () => forwardSignal('SIGTERM'));
  process.on('SIGINT', () => forwardSignal('SIGINT'));

  child.on('exit', (code, signal) => {
    if (signal) {
      process.kill(process.pid, signal);
      return;
    }
    if (code && code !== 0) {
      console.error(`[SpendSense] Server exited with non-zero code ${code}.`);
    }
    process.exit(code ?? 0);
  });
} catch (err) {
  console.error('[SpendSense] Server startup failed:', err?.stack || err?.message || err);
  process.exit(1);
}
