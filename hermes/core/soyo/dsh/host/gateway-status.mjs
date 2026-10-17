// SPDX-License-Identifier: MIT
// A persisted heartbeat is an observation, never a new transport/receipt probe.
export const GATEWAY_HEARTBEAT_MAX_AGE_SECONDS = 60;
export function gatewayHeartbeat(value, now = Date.now() / 1000) {
  const base = { evidence_source: 'native-gateway-heartbeat', actual_transport_probe: false,
    updated_at: null, status_age_seconds: null, observed_state: null, max_age_seconds: GATEWAY_HEARTBEAT_MAX_AGE_SECONDS };
  if (!value || typeof value !== 'object' || Array.isArray(value)) return { ...base, state: 'unavailable' };
  const stamp=value.updated_at;
  if (typeof stamp !== 'number' || !Number.isFinite(stamp) || stamp <= 0 || stamp > now + 5 ||
      !['connected','connecting','disconnected'].includes(value.state)) return { ...base, state: 'unknown' };
  const age=Math.max(0,now-stamp);
  return { ...base, updated_at: stamp, status_age_seconds: Math.round(age*100)/100, observed_state: value.state,
    state: age > GATEWAY_HEARTBEAT_MAX_AGE_SECONDS ? 'stale' : value.state };
}
