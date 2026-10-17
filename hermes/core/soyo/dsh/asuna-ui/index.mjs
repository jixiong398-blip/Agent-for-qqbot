// SPDX-License-Identifier: GPL-3.0-only
export const name = 'soyo-asuna-ui';
import z from '@deepseek-ai/schemastery';
export const inject = [];
const route = z.object({ provider: z.string(), model: z.string(), reasoningEffort: z.string(), maxTokens: z.natural().min(1).max(1048576) });
// These are native settings drafts, not live mutations of resident Agents.
// DSH only exposes volatile fields through settings.describe()/mutate().
export const Config = z.object({ routes: z.object({ character: route, action: route }).default({}).volatile() });
export function apply() {}
