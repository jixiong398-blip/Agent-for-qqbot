// SPDX-License-Identifier: MIT
// Retry only a pending local rename, never the effect which produced its bytes.
import { rename } from 'node:fs/promises';
import { setTimeout as delay } from 'node:timers/promises';

export async function replaceFile(source, target, { move = rename, wait = delay, windows = process.platform === 'win32' } = {}) {
  for (let attempt = 0; ; attempt++) {
    try { return await move(source, target); }
    catch (error) {
      // NTFS readers/virus scanners may briefly deny delete-sharing. Preserve
      // both files on permanent failure; do not unlink the selected target.
      if (!windows || !['EPERM', 'EACCES', 'EBUSY'].includes(error.code) || attempt >= 5) throw error;
      await wait(10 * 2 ** attempt);
    }
  }
}
