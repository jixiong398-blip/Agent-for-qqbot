// SPDX-License-Identifier: MIT
// The action lane may prepare an image, but only the character may attach it
// to the final QQ reply. A direct QQ image send from the action lane is a
// permanent dead end (action_not_allowlisted), so reject it before queuing.
export function imageSendObjective(objective) {
  if (typeof objective !== 'string') return false;
  const path = /(?:^|[\s"'`])(?:\/|~\/)[^\s"'`]+\.(?:png|jpe?g|webp|gif)\b/i.test(objective);
  const send = /(?:发送|发给|发到|直接发|试发|发图|send_(?:private|group)_msg)/i.test(objective);
  const qq = /(?:qq|私聊|群聊|主人)/i.test(objective);
  return path && send && qq;
}
