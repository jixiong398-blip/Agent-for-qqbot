// SPDX-License-Identifier: MIT
// Literal address boundary; forwarded headers and arbitrary hostnames grant nothing.

export function trustedUiHost(host) {
  return host === '127.0.0.1';
}

export function trustedUiPeer(address, host) {
  const peer = String(address ?? '').replace(/^::ffff:/, '');
  return trustedUiHost(host) && peer === '127.0.0.1';
}
