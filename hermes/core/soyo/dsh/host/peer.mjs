// SPDX-License-Identifier: MIT
// Compatibility entrypoint for the existing Peer plugin. GPT review reuses the
// fixed execution provider, but has fresh, tool-free contexts and its own ledger.
import { open } from 'node:fs/promises';
import { constants } from 'node:fs';
import z from '@deepseek-ai/schemastery';
import { GptReviews } from './gpt-reviews.mjs';
import { openPrivate } from './platform.mjs';

export const name = 'soyo-peer';
export const inject = ['agents', 'sessions', 'sessionQuery', 'sessionPersistence', 'workspaceRegistry',
  'tools', 'systemPrompt', 'llm', 'settings', 'soyoBrains'];
export const Config = z.object({ configFile: z.string().required() });
export async function apply(ctx, settings) {
  const file = await openPrivate(settings.configFile, 256 * 1024);
  let config;
  try {
    config = JSON.parse(await file.readFile('utf8'));
  } finally { await file.close(); }
  const service = new GptReviews(ctx, settings.configFile, config, ctx.soyoBrains.brains);
  await service.initialize();
}
