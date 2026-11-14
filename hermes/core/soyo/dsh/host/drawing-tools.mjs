// SPDX-License-Identifier: MIT
import { mkdir, realpath } from 'node:fs/promises';
import { join } from 'node:path';
import { createHash } from 'node:crypto';
import { defineTool } from '@deepseek-ai/dsh-tools';
import { imageMayGenerate, sceneImagePaths } from './image-policy.mjs';
import { generateImage, imageGenerationStatus, imageKeyFilePresent, loadReferenceImages } from './image-generation.mjs';

export function registerDrawingTools(scope, { config, current, owner, roots, generated, logger }) {
  const output = { schema: { type: 'object', additionalProperties: true }, render: (_a, value) => [{ type: 'text', text: JSON.stringify(value) }] };
  const allowed = trace => imageMayGenerate(config, { owner: owner(trace), envelope: trace.envelope,
    internal: Boolean(trace.internal && !trace.job?.binding?.owner_continuation) });
  scope.tools.register(defineTool({ name: 'soyo_draw_image',
    description: '可选绘图扩展：必须由部署用户提前配置独立 image_gen 凭据并开启当前场景权限。根据本轮明确绘图请求生成一张图；参考图最多四张，只能使用本场景已读取的原图或授权任务产物。会产生真实费用，失败不自动重试。行动脑只保存产物路径交回角色，QQ 仍由角色附图经唯一 writer 发送。',
    parameters: { prompt: { type: 'string', required: true }, size: { type: 'string' },
      reference_images: { type: 'array', items: { type: 'string' } } }, output,
    execute: async (args, exec) => {
      const trace = current(exec);
      if (!allowed(trace)) throw Error('IMAGE_PERMISSION: drawing is disabled for this original actor/scene');
      if (args.size !== undefined && typeof args.size !== 'string') throw Error('IMAGE_GEN_SIZE: explicit WIDTHxHEIGHT required');
      const paths = await sceneImagePaths(args.reference_images ?? [], trace.image_paths, owner(trace));
      const loaded = await loadReferenceImages({ paths, mediaRoot: config.media_root, extraRoots: roots(config) });
      if (loaded.error) return loaded.error;
      const mediaRoot = owner(trace) ? config.media_root : join(config.media_root, 'scene-generated',
        createHash('sha256').update(trace.envelope.route_id).digest('hex'));
      await mkdir(mediaRoot, { recursive: true, mode: 0o700 });
      const result = await generateImage({ config, prompt: args.prompt, size: args.size,
        referenceImages: loaded.images, mediaRoot, signal: exec.signal, logger });
      if (result.state === 'created') {
        trace.image_paths ??= new Set();
        trace.image_paths.add(await realpath(result.path));
        await generated?.(trace, result);
      }
      return { ...result, reference_images_used: loaded.images.length,
        note: result.state === 'created' ? '产物已保存；角色仍需 soyo_attach_image，平台回执才算送达。'
          : '没有已验证的出图成功；不自动重复付费请求。' };
    } }));
  scope.tools.register(defineTool({ name: 'soyo_image_status',
    description: '只读检查可选绘图扩展是否预先配置、当前场景是否获准；不调用绘图供应商，不返回 Key。', parameters: {}, output,
    execute: async (_args, exec) => {
      const trace = current(exec), status = imageGenerationStatus(config);
      return owner(trace) ? { ...status, allowed: allowed(trace), key_file_present: await imageKeyFilePresent(config) }
        : { configured: status.configured, allowed: allowed(trace), reference_images: true,
          note: '绘图需要部署配置与场景开关同时成立；不能读取主人收藏或其他场景图片。' };
    } }));
  return ['soyo_draw_image', 'soyo_image_status'];
}
