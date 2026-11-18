import { execFileSync } from 'node:child_process';
import { ensurePythonEnv } from './python_env.mjs';

try {
  const root = process.cwd();
  const pyBin = ensurePythonEnv(root, { fast: false });

  console.log('[SpendSense] Compiling Python bytecode...');
  execFileSync(pyBin, ['-m', 'compileall', '-q', 'app', 'data', 'tests'], {
    stdio: 'inherit',
    cwd: root,
  });

  console.log('[SpendSense] Production build complete.');
} catch (err) {
  console.error('[SpendSense] Build failed:', err?.stack || err?.message || err);
  process.exit(1);
}
