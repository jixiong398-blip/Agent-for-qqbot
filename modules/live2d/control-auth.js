'use strict';
const { timingSafeEqual } = require('node:crypto');
exports.authorized = (request, server) => {
  const authority = `127.0.0.1:${server.address()?.port}`;
  const key = process.env.LIVE2D_CONTROL_KEY;
  if (!key || key.length < 32 || request.headers.host !== authority ||
      request.headers.origin && request.headers.origin !== 'http://' + authority) return false;
  const received = Buffer.from(request.headers.authorization || ''), expected = Buffer.from('Bearer ' + key);
  return received.length === expected.length && timingSafeEqual(received, expected);
};
