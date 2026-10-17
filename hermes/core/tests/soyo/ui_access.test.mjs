// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { trustedUiHost, trustedUiPeer } from '../../soyo/dsh/host/ui-access.mjs';

test('product UI binds only loopback; remote maintenance is not an installation feature', () => {
  assert(trustedUiHost('127.0.0.1'));
  for (const host of ['0.0.0.0', '::', '::1', 'localhost', '192.168.1.2', '8.8.8.8', '100.64.0.1', '100.127.255.254', '100.128.0.1', '100.64.0.999', '0100.64.0.1'])
    assert.equal(trustedUiHost(host), false, host);
});

test('direct-entry admission uses actual TCP peer; loopback binding does not allow tailnet peers', () => {
  assert.equal(trustedUiPeer('100.64.0.2', '100.64.0.1'), false);
  assert.equal(trustedUiPeer('::ffff:100.64.0.2', '100.64.0.1'), false);
  assert(trustedUiPeer('::ffff:127.0.0.1', '127.0.0.1'));
  for (const peer of ['192.168.1.2', '8.8.8.8', undefined, '127.0.0.1, 100.64.0.2'])
    assert.equal(trustedUiPeer(peer, '100.64.0.1'), false);
  assert.equal(trustedUiPeer('100.64.0.2', '127.0.0.1'), false);
  assert.equal(trustedUiPeer('127.0.0.1', '0.0.0.0'), false);
});
