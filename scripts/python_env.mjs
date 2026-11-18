import { existsSync } from 'node:fs';
import { execFileSync, execSync } from 'node:child_process';
import { resolve } from 'node:path';

export const REQUIRED_PYTHON_IMPORTS = [
  'fastapi',
  'uvicorn',
  'jinja2',
  'babel',
  'pydantic_settings',
  'multipart',
  'sqlalchemy',
  'psycopg',
  'PIL',
  'argon2',
  'slowapi',
  'google.genai',
];

const IMPORT_CHECK_CODE = `import ${REQUIRED_PYTHON_IMPORTS.join(', ')}`;

export function resolveListenConfig(env = process.env) {
  const rawPort = typeof env.PORT === 'string' ? env.PORT.trim() : '';
  const port = rawPort && /^\d+$/.test(rawPort) ? rawPort : '3000';
  const rawHost = typeof env.HOST === 'string' ? env.HOST.trim() : '';
  const host = rawHost || '0.0.0.0';
  return { host, port };
}

export function buildUvicornArgs(env = process.env) {
  const { host, port } = resolveListenConfig(env);
  return [
    '-m',
    'uvicorn',
    'app.main:app',
    '--host',
    host,
    '--port',
    port,
    '--proxy-headers',
    '--forwarded-allow-ips',
    '*',
  ];
}

export function canImportAll(pythonBin) {
  if (!pythonBin) return false;
  if (pythonBin.includes('/') && !existsSync(pythonBin)) return false;
  try {
    execFileSync(pythonBin, ['-c', IMPORT_CHECK_CODE], { stdio: 'ignore' });
    return true;
  } catch {
    return false;
  }
}

export function findSystemPython311Plus() {
  const candidates = [process.env.PYTHON_BIN, '/usr/bin/python3', '/usr/local/bin/python3', 'python3'].filter(
    Boolean,
  );
  for (const bin of candidates) {
    try {
      execFileSync(bin, ['-c', 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)'], {
        stdio: 'ignore',
      });
      return bin;
    } catch {
      // Try next candidate
    }
  }
  return null;
}

export function findUv() {
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
    const found = execSync('command -v uv', { encoding: 'utf8' }).trim();
    return found || null;
  } catch {
    return null;
  }
}

export function bootstrapPythonEnv(root = process.cwd()) {
  const venvDir = resolve(root, '.venv');
  const venvPy = resolve(venvDir, 'bin', 'python');

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

  if (!existsSync(venvPy)) {
    const sysPy = findSystemPython311Plus();
    if (sysPy) {
      console.log(`[SpendSense] Creating virtualenv with ${sysPy}...`);
      execFileSync(uvBin, ['venv', '--python', sysPy, venvDir], { stdio: 'inherit', cwd: root });
    } else {
      console.log('[SpendSense] Creating Python 3.12 virtualenv...');
      execFileSync(uvBin, ['venv', '--python', '3.12', venvDir], { stdio: 'inherit', cwd: root });
    }
  }

  console.log('[SpendSense] Installing FastAPI server dependencies...');
  execFileSync(
    uvBin,
    ['pip', 'install', '--python', venvPy, '-r', resolve(root, 'requirements.txt')],
    {
      stdio: 'inherit',
      cwd: root,
      env: { ...process.env, UV_LINK_MODE: 'copy' },
    },
  );

  return venvPy;
}

export function ensurePythonEnv(root = process.cwd()) {
  const venvPy = resolve(root, '.venv', 'bin', 'python');
  if (canImportAll(venvPy)) {
    return venvPy;
  }

  // Fallback to a pre-installed system/container Python if it already has all packages
  const sysPy = findSystemPython311Plus();
  if (sysPy && canImportAll(sysPy)) {
    return sysPy;
  }

  return bootstrapPythonEnv(root);
}
