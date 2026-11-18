import test from 'node:test';
import assert from 'node:assert/strict';
import { buildUvicornArgs, resolveListenConfig } from './python_env.mjs';

test('resolveListenConfig defaults to 0.0.0.0 and port 3000', () => {
  assert.deepEqual(resolveListenConfig({}), { host: '0.0.0.0', port: '3000' });
  assert.deepEqual(resolveListenConfig({ PORT: '' }), { host: '0.0.0.0', port: '3000' });
  assert.deepEqual(resolveListenConfig({ PORT: 'invalid' }), { host: '0.0.0.0', port: '3000' });
});

test('resolveListenConfig uses PORT environment variable when set', () => {
  assert.deepEqual(resolveListenConfig({ PORT: '8080' }), { host: '0.0.0.0', port: '8080' });
  assert.deepEqual(resolveListenConfig({ PORT: '3000', HOST: '0.0.0.0' }), {
    host: '0.0.0.0',
    port: '3000',
  });
});

test('buildUvicornArgs binds to 0.0.0.0, reads PORT, and enables proxy headers', () => {
  const args = buildUvicornArgs({ PORT: '8080' });
  assert.deepEqual(args, [
    '-m',
    'uvicorn',
    'app.main:app',
    '--host',
    '0.0.0.0',
    '--port',
    '8080',
    '--proxy-headers',
    '--forwarded-allow-ips',
    '*',
  ]);
});
