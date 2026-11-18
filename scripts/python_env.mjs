import { accessSync, constants, existsSync } from 'node:fs';
import { execFileSync, execSync } from 'node:child_process';
import { tmpdir } from 'node:os';
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

const FAST_SPEC_CHECK_CODE = [
  'import importlib.util, sys',
  `mods = ${JSON.stringify(REQUIRED_PYTHON_IMPORTS)}`,
  'missing = [m for m in mods if importlib.util.find_spec(m) is None]',
  'sys.exit(0 if not missing else 1)',
].join('; ');

const FULL_IMPORT_CHECK_CODE = `import ${REQUIRED_PYTHON_IMPORTS.join(', ')}`;

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

export function isDirWritable(dirPath) {
  try {
    accessSync(dirPath, constants.W_OK | constants.X_OK);
    return true;
  } catch {
    return false;
  }
}

export function resolveVenvDir(root = process.cwd()) {
  const localVenv = resolve(root, '.venv');
  if (existsSync(localVenv) || isDirWritable(root)) {
    return localVenv;
  }
  return resolve(tmpdir(), 'spendsense-venv');
}

export function canImportAll(pythonBin, { fast = true } = {}) {
  if (!pythonBin) return false;
  if (pythonBin.includes('/') && !existsSync(pythonBin)) return false;
  try {
    execFileSync(pythonBin, ['-c', fast ? FAST_SPEC_CHECK_CODE : FULL_IMPORT_CHECK_CODE], {
      stdio: 'ignore',
    });
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

function installUv() {
  console.log('[SpendSense] Installing uv to bootstrap Python environment...');
  try {
    execSync('curl -LsSf https://astral.sh/uv/install.sh | sh', {
      stdio: 'inherit',
      env: { ...process.env, UV_UNMANAGED_INSTALL: '/tmp/uv-bin' },
    });
  } catch (curlErr) {
    const sysPy = findSystemPython311Plus();
    if (!sysPy) {
      throw curlErr;
    }
    console.warn('[SpendSense] curl uv installer unavailable, retrying via Python urllib...');
    execFileSync(
      sysPy,
      [
        '-c',
        [
          'import os, subprocess, urllib.request',
          'script = urllib.request.urlopen("https://astral.sh/uv/install.sh", timeout=20).read().decode("utf-8")',
          'env = {**os.environ, "UV_UNMANAGED_INSTALL": "/tmp/uv-bin"}',
          'subprocess.run(["sh"], input=script, text=True, env=env, check=True)',
        ].join('; '),
      ],
      { stdio: 'inherit' },
    );
  }
  const uvBin = findUv();
  if (!uvBin) {
    throw new Error('Failed to locate or install uv.');
  }
  return uvBin;
}

export function bootstrapPythonEnv(root = process.cwd()) {
  const venvDir = isDirWritable(root) ? resolve(root, '.venv') : resolve(tmpdir(), 'spendsense-venv');
  const venvPy = resolve(venvDir, 'bin', 'python');
  const uvPythonDir = resolve(tmpdir(), 'uv-python');

  const uvBin = findUv() || installUv();
  const sysPy = findSystemPython311Plus();
  const uvEnv = {
    ...process.env,
    UV_LINK_MODE: 'copy',
    UV_PYTHON_INSTALL_DIR: uvPythonDir,
  };

  if (sysPy) {
    console.log(`[SpendSense] Creating virtualenv at ${venvDir} with ${sysPy}...`);
    execFileSync(uvBin, ['venv', '--clear', '--python', sysPy, venvDir], {
      stdio: 'inherit',
      cwd: root,
      env: uvEnv,
    });
  } else {
    console.log(`[SpendSense] Creating Python 3.12 virtualenv at ${venvDir}...`);
    execFileSync(uvBin, ['venv', '--clear', '--python', '3.12', venvDir], {
      stdio: 'inherit',
      cwd: root,
      env: uvEnv,
    });
  }

  console.log('[SpendSense] Installing FastAPI server dependencies...');
  execFileSync(
    uvBin,
    ['pip', 'install', '--python', venvPy, '-r', resolve(root, 'requirements.txt')],
    {
      stdio: 'inherit',
      cwd: root,
      env: uvEnv,
    },
  );

  return venvPy;
}

export function ensurePythonEnv(root = process.cwd(), { fast = true } = {}) {
  const candidates = [
    resolve(root, '.venv', 'bin', 'python'),
    resolve(tmpdir(), 'spendsense-venv', 'bin', 'python'),
  ];

  for (const pyBin of candidates) {
    if (canImportAll(pyBin, { fast })) {
      return pyBin;
    }
  }

  const sysPy = findSystemPython311Plus();
  if (sysPy && canImportAll(sysPy, { fast })) {
    return sysPy;
  }

  return bootstrapPythonEnv(root);
}
