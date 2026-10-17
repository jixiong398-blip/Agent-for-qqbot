// SPDX-License-Identifier: MIT
// Fixed local broker seam; model text never chooses the interpreter or script.
import { spawn } from 'node:child_process';
import { workerEnvironment } from './platform.mjs';

export function developmentOperation(configFile, config, args, signal) {
  return new Promise((resolve, reject) => {
    const child = spawn(config.python, ['-B', config.development_script, configFile], { signal,
      env: workerEnvironment(), stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    let text = '', size = 0;
    const deadline = setTimeout(() => child.kill('SIGKILL'), 40000);
    child.stdout.on('data', chunk => { size += chunk.length; if (size > 256 * 1024) child.kill('SIGKILL'); else text += chunk; });
    child.stderr.resume(); child.stdin.on('error', () => {});
    child.on('error', () => { clearTimeout(deadline); reject(Error('Development broker unavailable')); });
    child.on('close', code => {
      clearTimeout(deadline);
      if (code !== 0) return reject(Error('Development broker interrupted; result unconfirmed'));
      try { resolve(JSON.parse(text)); } catch { reject(Error('Invalid development broker result')); }
    });
    child.stdin.end(JSON.stringify(args));
  });
}
