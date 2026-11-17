import { existsSync } from 'node:fs';
import { execSync, spawn } from 'node:child_process';
import { resolve } from 'node:path';

const root = process.cwd();
const venvDir = resolve(root, '.venv');
const uvicornBin = resolve(venvDir, 'bin', 'uvicorn');

function findUv() {
  const candidates = [
    process.env.UV_BIN,
    resolve(process.env.HOME || '/root', '.local/bin/uv'),
    '/usr/local/bin/uv',
    '/tmp/uv-bin/uv',
  ].filter(Boolean);

  for (const bin of candidates) {
    if (existsSync(bin)) return bin;
  }

  try {
    return execSync('command -v uv', { encoding: 'utf8' }).trim();
  } catch {
    return null;
  }
}

function bootstrapPythonEnv() {
  let uvBin = findUv();
  if (!uvBin) {
    console.log('[SpendSense] Installing uv to bootstrap Python environment...');
    execSync('curl -LsSf https://astral.sh/uv/install.sh | sh', {
      stdio: 'inherit',
      env: { ...process.env, UV_UNMANAGED_INSTALL: '/tmp/uv-bin' },
    });
    uvBin = findUv();
  }

  if (!uvBin) {
    throw new Error('Failed to locate or install uv.');
  }

  if (!existsSync(venvDir)) {
    console.log('[SpendSense] Creating Python 3.12 virtualenv...');
    execSync(`"${uvBin}" venv --python 3.12 "${venvDir}"`, { stdio: 'inherit' });
  }

  console.log('[SpendSense] Installing FastAPI server dependencies...');
  execSync(
    `"${uvBin}" pip install --python "${resolve(venvDir, 'bin/python')}" fastapi "uvicorn[standard]" jinja2 babel pydantic-settings python-multipart sqlalchemy argon2-cffi pillow slowapi pytest httpx`,
    { stdio: 'inherit' },
  );
}

if (!existsSync(uvicornBin)) {
  bootstrapPythonEnv();
}

const child = spawn(
  uvicornBin,
  ['app.main:app', '--host', '0.0.0.0', '--port', '3000'],
  { stdio: 'inherit', cwd: root },
);

process.on('SIGTERM', () => child.kill('SIGTERM'));
process.on('SIGINT', () => child.kill('SIGINT'));

child.on('exit', (code, signal) => {
  if (signal) process.kill(process.pid, signal);
  process.exit(code ?? 0);
});
