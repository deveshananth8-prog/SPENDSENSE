import { spawn } from 'node:child_process';
import { buildUvicornArgs, ensurePythonEnv, resolveListenConfig } from './python_env.mjs';

const root = process.cwd();
const pyBin = ensurePythonEnv(root);
const { host, port } = resolveListenConfig(process.env);
const uvicornArgs = buildUvicornArgs(process.env);

console.log(`[SpendSense] Starting server on ${host}:${port}...`);

const child = spawn(pyBin, uvicornArgs, {
  stdio: 'inherit',
  cwd: root,
  env: process.env,
});

child.on('error', (err) => {
  console.error('[SpendSense] Failed to spawn uvicorn:', err);
  process.exit(1);
});

process.on('SIGTERM', () => child.kill('SIGTERM'));
process.on('SIGINT', () => child.kill('SIGINT'));

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 0);
});
