// SPDX-License-Identifier: MIT
import assert from 'node:assert/strict';
import test from 'node:test';
import { imageSendObjective } from '../../soyo/dsh/host/image-send-guard.mjs';

test('the exact old direct-image-send objective is rejected before the action lane', () => {
  assert.equal(imageSendObjective('直接试发送：把 /tmp/soyo-mutsuki-from-ref.png 作为图片消息发到 QQ 私聊 100001。'), true);
  assert.equal(imageSendObjective('把 /path/out.png 发给主人'), true);
  assert.equal(imageSendObjective('用 send_private_msg 把 ~/a.jpg 发到 QQ'), true);
});

test('preparing or saving an image for the character remains a valid action task', () => {
  assert.equal(imageSendObjective('把 /tmp/source.png 保存到当前任务目录，并报告绝对路径。'), false);
  assert.equal(imageSendObjective('生成一张图片并保存到 development 任务目录，不要发送。'), false);
  assert.equal(imageSendObjective('查一下 QQ 发图权限和 action_not_allowlisted 的含义。'), false);
  assert.equal(imageSendObjective('检查图片尺寸和 sha256。'), false);
  assert.equal(imageSendObjective(''), false);
  assert.equal(imageSendObjective(null), false);
});
