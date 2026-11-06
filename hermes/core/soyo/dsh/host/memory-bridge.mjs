// SPDX-License-Identifier: MIT
// One bounded, private JSONL worker. Request ids prevent late replies from
// crossing callers. Never retry a possibly committed mutation automatically.
import { spawn } from 'node:child_process';
import { workerEnvironment } from './platform.mjs';
export class MemoryBridge {
  constructor(configFile, config) { Object.assign(this, { configFile, config }); this.queue = []; this.nextId = 0; }
  call(args, signal) {
    if (this.closed || this.queue.length >= 256) return Promise.reject(Error('Memory worker queue unavailable'));
    return new Promise((resolve, reject) => { this.queue.push({ id: ++this.nextId, args, signal, resolve, reject }); this.pump(); });
  }
  start() {
    const child = spawn(this.config.python, ['-B', this.config.memory_script, this.configFile, '--stream'], {
      env: workerEnvironment({ SOYO_CONFIG_FILE: this.configFile }), stdio: ['pipe', 'pipe', 'pipe'], windowsHide: true });
    this.child = child; let buffer = '';
    child.stderr.resume(); child.stdin.on('error', () => {});
    child.stdout.on('data', bytes => {
      buffer += bytes.toString('utf8');
      if (Buffer.byteLength(buffer) > 2 * 1024 * 1024) return child.kill();
      let newline;
      while ((newline = buffer.indexOf('\n')) >= 0) {
        const line = buffer.slice(0, newline); buffer = buffer.slice(newline + 1);
        try {
          const reply = JSON.parse(line), current = this.current;
          if (!current || reply.id !== current.id) { child.kill(); return; }
          this.current = null; clearTimeout(current.timer); current.signal?.removeEventListener('abort', current.abort);
          if (reply.error) current.reject(Error('Memory operation failed: ' + reply.error)); else current.resolve(reply.result);
          this.pump();
        } catch { child.kill(); }
      }
    });
    const ended = () => {
      if (this.child !== child) return; this.child = null;
      const current = this.current; this.current = null;
      if (current) { clearTimeout(current.timer); current.signal?.removeEventListener('abort', current.abort); current.reject(Error('Memory worker interrupted; outcome unconfirmed')); }
      if (!this.closed) setImmediate(() => this.pump());
    };
    child.on('error', ended); child.on('close', ended);
  }
  pump() {
    if (this.closed || this.current) return;
    let current;
    while ((current = this.queue.shift())) {
      if (current.signal?.aborted) { current.reject(current.signal.reason ?? Error('Aborted')); continue; }
      if (!this.child) this.start(); this.current = current;
      current.abort = () => this.child?.kill(); current.signal?.addEventListener('abort', current.abort, { once: true });
      current.timer = setTimeout(() => this.child?.kill(), 15000);
      this.child.stdin.write(JSON.stringify({ id: current.id, args: current.args }) + '\n'); break;
    }
  }
  close() { this.closed = true; this.child?.kill(); for (const entry of this.queue.splice(0)) entry.reject(Error('Memory bridge closed')); }
}
