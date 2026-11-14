// SPDX-License-Identifier: MIT
// Non-invasive fetch diagnostics. This observer never reads or clones a
// response body: production streaming, cancellation, backpressure and SDK
// metadata stay entirely under the provider adapter's ownership.

const MAX_REQUEST_BYTES = 256 * 1024;

export const safeDiagnostic = (value, max = 500) =>
  String(value?.message ?? value ?? '')
    .replace(/Bearer\s+\S+|sk-[A-Za-z0-9_-]{12,}/g, '<redacted>')
    .replace(/https?:\/\/\S+/g, '[endpoint]')
    .slice(0, max);

export function recordSseValue(record, value) {
  if (!value || typeof value !== 'object') return;
  if (typeof value.type === 'string') (record.sse_types ??= []).push(value.type);
  if (typeof value.item?.type === 'string') (record.output_item_types ??= []).push(value.item.type);
  if (value.type === 'response.function_call_arguments.done') {
    record.function_arguments_done = {
      has_arguments: Object.hasOwn(value, 'arguments'),
      arguments_length: typeof value.arguments === 'string' ? value.arguments.length : null,
    };
  }
  if (value.type === 'error' || value.error) {
    (record.sse_errors ??= []).push({
      type: value.type,
      error: safeDiagnostic(value.error?.message ?? value.message ?? value.error),
    });
  }
}

export function recordSseText(text, record) {
  let data = [];
  const flush = () => {
    const raw = data.join('\n').trim();
    data = [];
    if (!raw || raw === '[DONE]') return;
    try { recordSseValue(record, JSON.parse(raw)); }
    catch (error) { (record.sse_parse_errors ??= []).push(safeDiagnostic(error, 240)); }
  };
  for (const line of String(text).split(/\r?\n/)) {
    if (line === '') flush();
    else if (line.startsWith('data:')) data.push(line.slice(5).trimStart());
  }
  flush();
}

export function createResponseObserver({ fetch: realFetch = globalThis.fetch, validateRequest, onRequest } = {}) {
  const records = [];
  const observedFetch = async (input, init) => {
    const requestUrl = input instanceof Request ? input.url : String(input);
    const url = new URL(requestUrl);
    const method = String(init?.method ?? input?.method ?? 'GET').toUpperCase();
    const headers = new Headers(init?.headers ?? input?.headers);
    const record = { endpoint: url.origin + url.pathname, method,
      authorization_present: headers.has('authorization') };
    records.push(record);

    const body = typeof init?.body === 'string' ? init.body : undefined;
    let payload;
    if (body !== undefined && Buffer.byteLength(body) <= MAX_REQUEST_BYTES) {
      try {
        payload = JSON.parse(body);
        record.model = payload.model;
        record.fields = Object.keys(payload).sort();
        record.stream = payload.stream;
        record.max_output_tokens = payload.max_output_tokens;
        record.input_items = Array.isArray(payload.input) ? payload.input.length : null;
        record.input_types = Array.isArray(payload.input) ? payload.input.map(item => item.type ?? item.role) : [];
        record.tool_count = Array.isArray(payload.tools) ? payload.tools.length : 0;
      } catch (error) {
        record.request_parse_error = safeDiagnostic(error);
      }
    } else if (body !== undefined) {
      record.request_body_observation = 'skipped_over_limit';
    } else if (init?.body != null || input instanceof Request) {
      record.request_body_observation = 'skipped_non_string_body';
    }

    // Explicit endpoint/method/budget guards are safety gates, not optional
    // diagnostics. Their failure must prevent network I/O and remain visible.
    validateRequest?.({ url, method, headers, record, payload });

    try {
      onRequest?.({ url, method, headers, record, payload, bodyText: body });
    } catch (error) {
      record.observer_request_error = safeDiagnostic(error);
    }

    let response;
    try {
      response = await realFetch(input, init);
    } catch (error) {
      record.fetch_error = safeDiagnostic(error);
      throw error;
    }
    record.http_status = response.status;
    record.content_type = response.headers.get('content-type');
    return response;
  };

  return { fetch: observedFetch, records };
}
