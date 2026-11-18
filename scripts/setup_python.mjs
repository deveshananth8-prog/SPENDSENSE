import { execFileSync } from 'node:child_process';
import { ensurePythonEnv } from './python_env.mjs';

const root = process.cwd();
const pyBin = ensurePythonEnv(root);

console.log('[SpendSense] Compiling Python bytecode...');
execFileSync(pyBin, ['-m', 'compileall', '-q', 'app', 'data', 'tests'], {
  stdio: 'inherit',
  cwd: root,
});

console.log('[SpendSense] Production build complete.');
