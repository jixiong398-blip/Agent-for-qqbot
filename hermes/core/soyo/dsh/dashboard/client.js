// SPDX-License-Identifier: MIT
// Native DSH settings: scoped styles, authenticated operator RPC, no iframe or remote assets.
window.__ModuleLoader__.load({
  id: '@soyo/dsh-dashboard',
  factory: require => {
    const React = require('react');
    const h = React.createElement;
    let setupConnection;
    const STYLES = `
.bqs-dialog {
  --bqs-bg: var(--dsw-alias-bg-base, #fff);
  --bqs-ink: var(--dsw-alias-label-primary, #24232b);
  --bqs-muted: color-mix(in srgb, var(--bqs-ink) 62%, var(--bqs-bg));
  --bqs-line: color-mix(in srgb, var(--bqs-ink) 10%, var(--bqs-bg));
  --bqs-soft: color-mix(in srgb, var(--bqs-ink) 3%, var(--bqs-bg));
  --bqs-purple: color-mix(in srgb, #9a65db 85%, var(--bqs-ink));
  --bqs-blue: color-mix(in srgb, #598bea 80%, var(--bqs-ink));
  --bqs-purple-soft: color-mix(in srgb, #a570ed 10%, var(--bqs-bg));
  --bqs-blue-soft: color-mix(in srgb, #5291fb 9%, var(--bqs-bg));
  width: min(1080px, calc(100vw - 64px)); height: min(820px, calc(100dvh - 64px));
  max-width: none; max-height: none; padding: 0; margin: auto; overflow: hidden;
  border: 1px solid var(--bqs-line); border-radius: 22px; background: var(--bqs-bg); color: var(--bqs-ink);
  box-shadow: 0 28px 100px #17132920, 0 4px 20px #17132908;
  font: 14px/1.6 -apple-system, BlinkMacSystemFont, 'Segoe UI', 'Microsoft YaHei', sans-serif;
  text-align: left; color-scheme: inherit;
}
.bqs-dialog::backdrop { background: #19172439; backdrop-filter: blur(5px); }
.bqs-dialog *, .bqs-dialog *::before, .bqs-dialog *::after { box-sizing: border-box; }
.bqs-dialog button, .bqs-dialog input, .bqs-dialog select, .bqs-dialog textarea { font: inherit; }
.bqs-dialog button, .bqs-dialog a, .bqs-dialog summary { -webkit-tap-highlight-color: transparent; }
.bqs-dialog button { cursor: pointer; }
.bqs-dialog button:disabled, .bqs-dialog fieldset:disabled .bqs-import { cursor: not-allowed; opacity: .45; }
.bqs-dialog :focus-visible { outline: 3px solid color-mix(in srgb, #9b6add 40%, transparent); outline-offset: 3px; }
.bqs-dialog h2, .bqs-dialog h3, .bqs-dialog p { margin: 0; }
.bqs-dialog p { overflow-wrap: anywhere; }
.bqs-dialog svg, .bqs-launch svg { flex: none; display: block; }
.bqs-shell { height: 100%; display: flex; flex-direction: column; min-height: 0; }
.bqs-top { flex: none; display: flex; align-items: center; gap: 13px; padding: 22px 26px; border-bottom: 1px solid var(--bqs-line); }
.bqs-mark { width: 40px; height: 40px; border: 1px solid color-mix(in srgb, #9b6add 18%, var(--bqs-bg)); border-radius: 13px;
  display: grid; place-items: center; background: var(--bqs-purple-soft); color: var(--bqs-purple); }
.bqs-top-title { font-size: 17px; font-weight: 650; letter-spacing: -.3px; line-height: 1.4; }
.bqs-top-caption { margin-top: 2px !important; color: var(--bqs-muted); font-size: 12px; }
.bqs-top-end { margin-left: auto; display: flex; align-items: center; gap: 17px; }
.bqs-icon-button { display: inline-flex; align-items: center; justify-content: center; width: 32px; height: 32px; border: 0;
  border-radius: 9px; color: var(--bqs-muted); background: transparent; padding: 0; }
.bqs-icon-button:hover { background: var(--bqs-soft); color: var(--bqs-ink); }
.bqs-state { display: inline-flex; gap: 7px; align-items: center; color: var(--bqs-muted); font-size: 12px; white-space: nowrap; }
.bqs-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: none; opacity: .6; }
.bqs-state[data-state="ready"] .bqs-dot { color: #52a47c; opacity: 1; }
.bqs-state[data-state="dirty"] { color: var(--bqs-purple); }
.bqs-layout { display: flex; flex: 1; min-height: 0; }
.bqs-aside { width: 204px; flex: none; display: flex; flex-direction: column; padding: 24px 14px 20px; border-right: 1px solid var(--bqs-line); }
.bqs-nav-label { padding: 0 14px 12px; font-size: 11px; font-weight: 600; color: var(--bqs-muted); letter-spacing: 1.2px; }
.bqs-nav { display: grid; gap: 6px; }
.bqs-nav-button { position: relative; width: 100%; display: flex; align-items: center; gap: 12px; padding: 13px 14px;
  border: 0; border-radius: 11px; text-align: left; color: var(--bqs-muted); background: transparent; }
.bqs-nav-button:hover { color: var(--bqs-ink); background: var(--bqs-soft); }
.bqs-nav-button[aria-pressed="true"] { background: var(--bqs-purple-soft); color: var(--bqs-purple); }
.bqs-nav-button[aria-pressed="true"]::before { content: ''; position: absolute; left: -14px; width: 3px; height: 23px; border-radius: 0 3px 3px 0; background: var(--bqs-purple); }
.bqs-nav-title { display: block; font-size: 13px; font-weight: 600; line-height: 1.5; }
.bqs-nav-caption { display: block; font-size: 11px; color: var(--bqs-muted); margin-top: 2px; }
.bqs-local { display: flex; gap: 8px; align-items: flex-start; padding: 18px 13px 0; margin-top: auto; color: var(--bqs-muted); font-size: 11px; line-height: 1.6; }
.bqs-local svg { margin-top: 2px; opacity: .7; }
.bqs-form { flex: 1; min-width: 0; display: flex; flex-direction: column; min-height: 0; margin: 0; }
.bqs-scroll { flex: 1; min-height: 0; overflow-y: auto; overscroll-behavior: contain; scrollbar-width: thin;
  scrollbar-color: var(--bqs-line) transparent; padding: 30px 34px 32px; }
.bqs-intro { margin-bottom: 25px; }
.bqs-intro h2 { font-size: 23px; font-weight: 650; letter-spacing: -.6px; line-height: 1.5; }
.bqs-intro p { margin-top: 5px; font-size: 13px; color: var(--bqs-muted); }
.bqs-fields { min-width: 0; padding: 0; margin: 0; border: 0; display: grid; gap: 18px; }
.bqs-card { border: 1px solid var(--bqs-line); border-radius: 15px; min-width: 0; overflow: hidden; }
.bqs-card-head { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; padding: 19px 21px 0; }
.bqs-card-title { display: flex; align-items: center; gap: 9px; font-size: 14px; font-weight: 600; }
.bqs-card-caption { padding: 6px 21px 0; font-size: 12px; color: var(--bqs-muted); }
.bqs-card-body { padding: 19px 21px 21px; min-width: 0; }
.bqs-card-tail { background: var(--bqs-soft); border-top: 1px solid var(--bqs-line); padding: 12px 21px; font-size: 12px; color: var(--bqs-muted); }
.bqs-pill { display: inline-flex; align-items: center; gap: 5px; width: fit-content; border-radius: 20px; padding: 3px 9px; font-size: 11px; line-height: 1.6; font-weight: 500; color: var(--bqs-muted); background: var(--bqs-soft); }
.bqs-pill[data-tone="purple"] { color: var(--bqs-purple); background: var(--bqs-purple-soft); }
.bqs-pill[data-tone="blue"] { color: var(--bqs-blue); background: var(--bqs-blue-soft); }
.bqs-pill[data-tone="green"] { color: #33835a; background: color-mix(in srgb, #62bb8b 9%, var(--bqs-bg)); }
.bqs-head-action { margin-left: auto; }
.bqs-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 17px 18px; }
.bqs-stack { display: grid; gap: 18px; min-width: 0; }
.bqs-field { display: flex; flex-direction: column; min-width: 0; gap: 7px; }
.bqs-field-label { font-size: 12px; font-weight: 500; display: flex; align-items: center; gap: 7px; }
.bqs-hint { display: block; font-size: 11px; font-weight: 400; color: var(--bqs-muted); line-height: 1.7; overflow-wrap: anywhere; }
.bqs-control { width: 100%; min-width: 0; height: 39px; border: 1px solid var(--bqs-line); border-radius: 9px; padding: 9px 11px;
  background: var(--bqs-bg); color: var(--bqs-ink); outline: none; transition: border-color .15s, box-shadow .15s; font-size: 13px !important; }
.bqs-control::placeholder { color: var(--bqs-muted); opacity: .65; }
.bqs-control:hover { border-color: color-mix(in srgb, var(--bqs-ink) 22%, var(--bqs-bg)); }
.bqs-control:focus { border-color: #a17bd6; box-shadow: 0 0 0 3px color-mix(in srgb, #a17bd6 12%, transparent); }
.bqs-control:disabled { background: var(--bqs-soft); cursor: not-allowed; }
select.bqs-control { appearance: none; padding-right: 34px; cursor: pointer; }
.bqs-select { display: block; position: relative; min-width: 0; }
.bqs-select > svg { position: absolute; right: 12px; top: 12px; pointer-events: none; color: var(--bqs-muted); }
.bqs-textarea { min-height: 230px; height: auto; resize: vertical; line-height: 1.85; padding: 15px; font-family: inherit; }
.bqs-code { font-family: ui-monospace, SFMono-Regular, Consolas, monospace !important; font-size: 12px !important; }
.bqs-row { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.bqs-row-between { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.bqs-button { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-height: 35px; padding: 7px 12px;
  border: 1px solid var(--bqs-line); border-radius: 9px; background: var(--bqs-bg); color: var(--bqs-ink); font-size: 12px !important;
  font-weight: 500 !important; line-height: 1.5; text-decoration: none; transition: background .15s, border-color .15s; }
.bqs-button:hover:not(:disabled) { background: var(--bqs-soft); border-color: color-mix(in srgb, var(--bqs-ink) 20%, var(--bqs-bg)); }
.bqs-button[data-variant="primary"] { background: #7951b9; border-color: #7951b9; color: #fff; }
.bqs-button[data-variant="primary"]:hover:not(:disabled) { background: #6943a8; border-color: #6943a8; }
.bqs-button[data-variant="soft"] { color: var(--bqs-purple); background: var(--bqs-purple-soft); border-color: transparent; }
.bqs-button[data-variant="ghost"] { border-color: transparent; color: var(--bqs-muted); background: transparent; padding-inline: 7px; }
.bqs-button[data-variant="danger"] { color: #bc5f61; }
.bqs-button[data-variant="link"] { color: var(--bqs-blue); background: transparent; border-color: transparent; padding-inline: 2px; }
.bqs-button svg { width: 15px; height: 15px; }
.bqs-switch-row { display: flex; gap: 16px; justify-content: space-between; align-items: center; cursor: pointer; }
.bqs-switch-text { display: grid; gap: 4px; font-size: 13px; font-weight: 500; }
.bqs-switch { display: inline-flex; align-items: center; position: relative; flex: none; width: 34px; height: 20px; }
.bqs-switch input { position: absolute; inset: 0; width: 100%; height: 100%; opacity: 0; margin: 0; cursor: pointer; z-index: 1; }
.bqs-switch-track { display: block; width: 34px; height: 20px; border-radius: 12px; background: color-mix(in srgb, var(--bqs-ink) 20%, var(--bqs-bg)); transition: background .15s; }
.bqs-switch-track::after { content: ''; position: absolute; left: 3px; top: 3px; width: 14px; height: 14px; border-radius: 50%; background: #fff; box-shadow: 0 1px 3px #0002; transition: transform .15s; }
.bqs-switch input:checked + .bqs-switch-track { background: #8d65c7; }
.bqs-switch input:checked + .bqs-switch-track::after { transform: translateX(14px); }
.bqs-switch input:focus-visible + .bqs-switch-track { outline: 3px solid #ae86e470; outline-offset: 3px; }
.bqs-switch input:disabled { cursor: not-allowed; }
.bqs-switch input:disabled + .bqs-switch-track { opacity: .45; }
.bqs-shared { display: flex; gap: 12px; align-items: center; border-radius: 10px; background: var(--bqs-soft); padding: 12px 14px; margin-top: 17px; }
.bqs-shared > svg { color: var(--bqs-blue); }
.bqs-shared p { font-size: 12px; font-weight: 500; }
.bqs-disclosure { border-top: 1px solid var(--bqs-line); padding-top: 13px; margin-top: 18px; min-width: 0; }
.bqs-disclosure > summary { list-style: none; display: flex; align-items: center; gap: 6px; min-height: 24px; cursor: pointer; font-size: 13px; line-height: 24px; color: var(--dsw-alias-label-tertiary, var(--bqs-muted)); transition: color 100ms ease; }
.bqs-disclosure > summary:hover { color: var(--dsw-alias-label-secondary, var(--bqs-ink)); }
.bqs-disclosure > summary::-webkit-details-marker { display: none; }
.bqs-disclosure > summary:focus-visible { outline: 2px solid var(--bqs-purple); outline-offset: 3px; border-radius: 6px; }
.bqs-disclosure > summary > svg { flex: none; width: 14px; height: 14px; transform: rotate(90deg); transition: transform 120ms ease; }
.bqs-disclosure[open] > summary > svg { transform: rotate(-90deg); }
.bqs-disclosure > .bqs-stack { padding-top: 14px; }
.bqs-summary-note { margin-left: auto; color: var(--bqs-muted); font-size: 12px; }
.bqs-editor-head { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding-bottom: 10px; }
.bqs-editor-meta { font-size: 11px; color: var(--bqs-muted); }
.bqs-import { display: inline-flex; position: relative; align-items: center; gap: 6px; cursor: pointer; }
.bqs-import input { position: absolute; inset: 0; opacity: 0; width: 100%; cursor: pointer; }
.bqs-import:focus-within { outline: 3px solid #ae86e470; outline-offset: 3px; }
.bqs-persona-preview { width: 36px; height: 36px; display: grid; place-items: center; border-radius: 12px; color: var(--bqs-purple); background: var(--bqs-purple-soft); font-size: 17px; font-weight: 600; }
.bqs-app { display: flex; align-items: center; gap: 13px; }
.bqs-app-icon { width: 44px; height: 44px; border-radius: 13px; background: var(--bqs-blue-soft); color: var(--bqs-blue); display: grid; place-items: center; }
.bqs-app h3 { font-size: 16px; font-weight: 600; }
.bqs-app p { font-size: 12px; color: var(--bqs-muted); margin-top: 1px; }
.bqs-status-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1px; background: var(--bqs-line); border: 1px solid var(--bqs-line); border-radius: 11px; overflow: hidden; margin: 20px 0; }
.bqs-status-cell { background: var(--bqs-soft); padding: 12px 15px; display: grid; gap: 4px; }
.bqs-status-cell > span:first-child { color: var(--bqs-muted); font-size: 11px; }
.bqs-status-value { display: flex; align-items: center; gap: 7px; font-size: 13px; }
.bqs-steps { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 18px; color: var(--bqs-muted); font-size: 11px; }
.bqs-step { display: inline-flex; align-items: center; gap: 6px; }
.bqs-step b { width: 18px; height: 18px; border: 1px solid var(--bqs-line); border-radius: 50%; font-size: 10px; font-weight: 500; display: grid; place-items: center; }
.bqs-step-line { color: var(--bqs-line); }
.bqs-empty { padding: 19px; background: var(--bqs-soft); border-radius: 10px; text-align: center; color: var(--bqs-muted); font-size: 12px; }
.bqs-notice { display: flex; gap: 8px; align-items: flex-start; padding: 11px 14px; margin: 0 0 18px; border-radius: 10px;
  background: var(--bqs-purple-soft); color: var(--bqs-purple); font-size: 12px; overflow-wrap: anywhere; }
.bqs-notice svg { margin-top: 2px; }
.bqs-notice[data-kind="error"] { color: #b45155; background: color-mix(in srgb, #d26670 8%, var(--bqs-bg)); }
.bqs-footer { flex: none; border-top: 1px solid var(--bqs-line); padding: 17px 28px; display: flex; align-items: center; gap: 12px; background: var(--bqs-bg); }
.bqs-footer-note { font-size: 11px; color: var(--bqs-muted); display: flex; align-items: center; gap: 6px; margin-right: auto; }
.bqs-footer .bqs-button[data-variant="primary"] { min-height: 38px; padding-inline: 17px; }
.bqs-skeleton { display: grid; gap: 18px; padding: 30px; }
.bqs-skeleton span { height: 40px; border-radius: 10px; background: var(--bqs-soft); }
.bqs-skeleton span:nth-child(2) { height: 180px; }
.bqs-launch { display: inline-flex; align-items: center; justify-content: center; gap: 7px; min-width: 32px; height: 32px; padding: 6px 8px;
  border: 0; border-radius: 8px; color: inherit; background: transparent; font: inherit; font-size: 12px; cursor: pointer; }
.bqs-launch:hover { background: var(--dsw-alias-bg-layer-2, #f3f3f5); }
.bqs-launch:focus-visible { outline: 2px solid #a17bd6; outline-offset: 2px; }
@media (max-width: 800px) {
  .bqs-dialog { width: calc(100vw - 32px); height: calc(100dvh - 32px); border-radius: 18px; }
  .bqs-aside { width: 174px; padding-inline: 10px; }
  .bqs-nav-button { padding-inline: 11px; gap: 9px; }
  .bqs-nav-button[aria-pressed="true"]::before { left: -10px; }
  .bqs-scroll { padding: 25px 24px; }
  .bqs-grid { column-gap: 14px; }
  .bqs-footer-note { display: none; }
  .bqs-footer { justify-content: flex-end; padding: 16px 24px; }
}
@media (max-width: 600px) {
  .bqs-dialog { width: calc(100vw - 16px); height: calc(100dvh - 24px); border-radius: 17px; }
  .bqs-top { padding: 17px 18px; gap: 10px; }
  .bqs-top-title { font-size: 16px; } .bqs-top-caption { font-size: 11px; }
  .bqs-mark { width: 34px; height: 34px; border-radius: 11px; }
  .bqs-top-end { gap: 10px; } .bqs-top-end .bqs-state { font-size: 10px; gap: 5px; }
  .bqs-layout { flex-direction: column; }
  .bqs-aside { width: 100%; padding: 10px 14px; border-right: 0; border-bottom: 1px solid var(--bqs-line); }
  .bqs-nav-label, .bqs-local, .bqs-nav-caption { display: none; }
  .bqs-nav { display: flex; gap: 4px; }
  .bqs-nav-button { flex: 1; justify-content: center; padding: 9px 4px; gap: 6px; border-radius: 8px; }
  .bqs-nav-button svg { width: 15px; height: 15px; }
  .bqs-nav-title { font-size: 12px; font-weight: 500; white-space: nowrap; }
  .bqs-nav-button[aria-pressed="true"]::before { display: none; }
  .bqs-scroll { padding: 23px 17px; }
  .bqs-intro { margin-bottom: 21px; } .bqs-intro h2 { font-size: 21px; }
  .bqs-intro p { font-size: 12px; } .bqs-fields { gap: 15px; }
  .bqs-card { border-radius: 13px; }
  .bqs-card-head { padding: 16px 16px 0; } .bqs-card-caption { padding-inline: 16px; }
  .bqs-card-body { padding: 17px 16px; } .bqs-card-tail { padding: 12px 16px; }
  .bqs-grid { grid-template-columns: minmax(0, 1fr); gap: 16px; }
  .bqs-control { height: 41px; font-size: 14px !important; }
  .bqs-summary-note { max-width: 55%; text-align: right; }
  .bqs-card-head .bqs-head-action { margin-left: auto; }
  .bqs-card-head .bqs-head-action .bqs-button { padding-inline: 4px; font-size: 11px !important; }
  .bqs-footer { gap: 8px; padding: 13px 16px max(13px, env(safe-area-inset-bottom)); }
  .bqs-footer .bqs-button { font-size: 11px !important; }
  .bqs-footer > .bqs-button[data-variant="ghost"] { margin-right: auto; }
  .bqs-footer .bqs-button[data-variant="primary"] { padding-inline: 12px; }
  .bqs-status-cell { padding: 11px 13px; }
  .bqs-row-between { gap: 10px; }
}
@media (prefers-reduced-motion: reduce) { .bqs-dialog * { transition: none !important; scroll-behavior: auto !important; } }
  .bqs-page { display: flex; flex-direction: column; min-height: 0; }
  .bqs-page .bqs-top { padding: 0 0 16px; }
  .bqs-page .bqs-scroll { padding: 0; overflow: visible; flex: 1; }
  .bqs-page .bqs-footer { padding: 16px 0 0; background: transparent; }
  .bqs-service-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 0; border-top: 1px solid var(--bqs-line); }
  .bqs-service-row:first-child { border-top: 0; }
  .bqs-service-name { display: block; font-size: 13px; font-weight: 500; }
  .bqs-logs { margin: 0; padding: 12px 14px; max-height: 320px; overflow: auto; border: 1px solid var(--bqs-line); border-radius: 11px; background: var(--bqs-soft); font: 12px/1.6 ui-monospace, monospace; white-space: pre-wrap; overflow-wrap: anywhere; }
`;
    const ICONS = {
      layers: ['m12 3 9 5-9 5-9-5 9-5Z', 'm3 12 9 5 9-5', 'm3 16 9 5 9-5'],
      model: ['M8 3H5a2 2 0 0 0-2 2v3m13-5h3a2 2 0 0 1 2 2v3M3 16v3a2 2 0 0 0 2 2h3m8 0h3a2 2 0 0 0 2-2v-3', 'M8 8h8v8H8z'],
      user: ['M20 21v-2a6 6 0 0 0-6-6h-4a6 6 0 0 0-6 6v2', 'M16 6a4 4 0 1 1-8 0 4 4 0 0 1 8 0Z'],
      plug: ['m8 3 1 4m6-5 1 4', 'm6 8 12-3 1 5a6 6 0 0 1-11 3L6 8Z', 'm13 16 1 3a3 3 0 0 1-2 4'],
      close: ['m6 6 12 12M18 6 6 18'], check: ['m5 12 4 4L19 6'],
      chevron: ['m9 5 7 7-7 7'], down: ['m6 9 6 6 6-6'],
      link: ['m10 13 4-2', 'm8 16-2 1a4 4 0 0 1-4-7l5-3a4 4 0 0 1 5 1m4 0 2-1a4 4 0 0 1 4 7l-5 3a4 4 0 0 1-5-1'],
      external: ['M14 3h7v7m0-7L10 14', 'M10 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-5'],
      refresh: ['M20 7a8 8 0 1 0 1 8', 'M20 2v6h-6'],
      key: ['M9 15a6 6 0 1 1 3-3l-8 8H1v-3l8-8'],
      shield: ['m12 3 8 3v6c0 5-8 9-8 9s-8-4-8-9V6l8-3Z', 'm8 12 3 3 5-6'],
      upload: ['M12 16V3m-4 4 4-4 4 4', 'M4 15v5a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-5'],
      save: ['M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h12l4 4v12a2 2 0 0 1-2 2Z', 'M7 3v6h10V3M7 21v-8h10v8'],
      arrow: ['M4 12h16m-5-5 5 5-5 5'], info: ['M12 11v6m0-10v.01', 'M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z'],
      play: ['m9 5 11 7-11 7V5Z'], folder: ['M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z'],
    };
    const icon = (name, size = 18) => h('svg', { width: size, height: size, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor',
      strokeWidth: 1.6, strokeLinecap: 'round', strokeLinejoin: 'round', 'aria-hidden': true },
      ...(ICONS[name] || ICONS.info).map((d, key) => h('path', { d, key })));
    const pill = (label, tone) => h('span', { className: 'bqs-pill', 'data-tone': tone }, label);
    const routeDraft = value => ({ name: '', base_url: '', auth_mode: 'bearer', api: 'openai-completions',
      context_window: 32768, max_tokens: 4096, reasoning_effort: '', vision: false, reasoning_efforts: {}, ...value,
      api_key: '', mappingText: JSON.stringify(value?.reasoning_efforts || {}) });
    const TABS = [
      { id: 'models', label: '模型与脑区', caption: '供应商与双脑协作', icon: 'layers', description: '为对话和行动选择合适的模型，让两个脑各司其职。' },
      { id: 'persona', label: '角色设定', caption: '名字、性格与表达', icon: 'user', description: '从一个名字开始，定义只属于你的 Bot。' },
      { id: 'qq', label: 'QQ / NapCat', caption: '账号登录与连接', icon: 'plug', description: '可以先聊一聊，再决定是否将 Bot 接入 QQ。' },
    ];

    function NativeSetup({ pageTab = 'models' }) {
      const [tab, setTab] = React.useState(pageTab);
      const [sample, setSample] = React.useState(null), [draft, setDraft] = React.useState(null);
      const [text, setText] = React.useState(''), [notice, setNotice] = React.useState(''), [noticeKind, setNoticeKind] = React.useState('info');
      const [busy, setBusy] = React.useState(false), [account, setAccount] = React.useState('');
      const [modelProfile, setModelProfile] = React.useState(''), [saveProfileName, setSaveProfileName] = React.useState('');
      const [personaPreset, setPersonaPreset] = React.useState(''), [savePersonaName, setSavePersonaName] = React.useState('');
      const scroll = React.useRef(null), baseline = React.useRef('');
      const pending = ['queued', 'applying'].includes(sample?.operation?.phase);
      const call = async (method, request) => {
        const result = await setupConnection.rpc.call('/api', 'botSetup/' + method, { args: request === undefined ? {} : { request } });
        if (!result.ok) throw Error(result.error?.message || '配置操作未完成'); return result.value;
      };
      const load = async (replace = false) => {
        const value = await call('view'); setSample(value);
        if (replace) {
          const c = value.config;
          const next = { character_name: c.character_name || 'Bot', action_uses_character: c.action_uses_character,
            host_permission_mode: c.host_permission_mode, time_zone: c.time_zone || '',
            models: { character: routeDraft(c.models.character), action: routeDraft(c.models.action) }, onebot: { ...c.onebot, token: '' } };
          const soul = value.persona.text || '# Bot\n\n你是 Bot。名字、性格、语言和背景由使用者自行定义；没有固定人物设定。\n不知道时说明不知道；以真实工具结果和平台回执核对完成状态。';
          setDraft(next); setText(soul); setAccount(c.onebot.account_id || value.napcat.accounts[0]?.account_id || '');
          setModelProfile(''); setSaveProfileName('');
          baseline.current = JSON.stringify({ draft: next, text: soul, modelProfile: '', saveProfileName: '' });
        }
        return value;
      };
      React.useEffect(() => { load(true)
        .catch(error => { setNoticeKind('error'); setNotice(error.message); }); }, []);
      React.useEffect(() => { scroll.current?.scrollTo({ top: 0 }); }, [tab]);
      React.useEffect(() => {
        if (!pending) return;
        const timer = setInterval(() => { load().then(value => {
          if (value.operation.phase === 'applied') location.reload();
          else if (value.operation.phase === 'failed') { setNoticeKind('error'); setNotice('应用未完成，原配置和恢复证据保留；请重新读取后核对。'); }
        }).catch(() => setNotice('原生 DSH 正在重连，请稍候…')); }, 2000);
        return () => clearInterval(timer);
      }, [pending]);
      const run = async work => {
        setBusy(true); setNoticeKind('info'); setNotice('正在处理…');
        try { await work(); } catch (error) { setNoticeKind('error'); setNotice(error.message); } finally { setBusy(false); }
      };
      const field = (label, value, change, { type = 'text', options, hint, placeholder, display = label, code = false } = {}) => {
        const props = { className: 'bqs-control' + (code ? ' bqs-code' : ''), 'aria-label': label, value,
          disabled: busy || pending, onChange: event => change(type === 'number' ? Number(event.target.value) : event.target.value) };
        return h('label', { className: 'bqs-field' }, h('span', { className: 'bqs-field-label' }, display),
          options ? h('span', { className: 'bqs-select' }, h('select', props, ...options.map(([v, name]) => h('option', { key: v, value: v }, name))), icon('down', 14))
            : h('input', { ...props, type, placeholder, autoComplete: type === 'password' ? 'new-password' : 'off', ...(type === 'number' ? { min: 1, step: 1 } : {}) }),
          hint && h('span', { className: 'bqs-hint' }, hint));
      };
      const set = (key, value) => setDraft(old => ({ ...old, [key]: value }));
      const laneSet = (lane, key, value) => setDraft(old => ({ ...old, models: { ...old.models, [lane]: { ...old.models[lane], [key]: value } } }));
      const onebotSet = (key, value) => setDraft(old => ({ ...old, onebot: { ...old.onebot, [key]: value } }));
      const button = (label, action, { disabled = false, variant = 'default', glyph, aria = label } = {}) => h('button', {
        type: 'button', className: 'bqs-button', 'data-variant': variant, 'aria-label': aria, disabled: busy || pending || disabled,
        onClick: () => run(action),
      }, glyph && icon(glyph, 15), label);
      const toggle = (label, checked, change, { hint, aria = label } = {}) => h('label', { className: 'bqs-switch-row' },
        h('span', { className: 'bqs-switch-text' }, label, hint && h('span', { className: 'bqs-hint' }, hint)),
        h('span', { className: 'bqs-switch' }, h('input', { type: 'checkbox', 'aria-label': aria, checked, disabled: busy || pending,
          onChange: e => change(e.target.checked) }), h('span', { className: 'bqs-switch-track', 'aria-hidden': true })));
      const disclosure = (title, body, note) => h('details', { className: 'bqs-disclosure' },
        h('summary', {}, icon('chevron', 14), title, note && h('span', { className: 'bqs-summary-note' }, note)), h('div', { className: 'bqs-stack' }, body));
      const card = (title, body, { glyph, caption, action, tail } = {}) => h('section', { className: 'bqs-card' },
        h('div', { className: 'bqs-card-head' }, h('h3', { className: 'bqs-card-title' }, glyph && icon(glyph, 16), title), action && h('div', { className: 'bqs-head-action' }, action)),
        caption && h('p', { className: 'bqs-card-caption' }, caption), h('div', { className: 'bqs-card-body' }, body),
        tail && h('div', { className: 'bqs-card-tail' }, tail));
      const lane = name => {
        const value = draft.models[name], character = name === 'character';
        return card(pill(character ? '角色脑' : '行动脑', character ? 'purple' : 'blue'), h(React.Fragment, {},
          h('div', { className: 'bqs-grid' },
            field('模型 ID', value.name, v => laneSet(name, 'name', v), { placeholder: '填写供应商提供的模型 ID', code: true }),
            field('供应商 API Base URL', value.base_url, v => laneSet(name, 'base_url', v), { type: 'url', display: 'API 地址', placeholder: 'https://api.example.com/v1', code: true }),
            field('协议', value.api, v => laneSet(name, 'api', v), { options: [['openai-completions', 'Chat Completions'], ['openai-responses', 'Responses']] }),
            field('认证方式', value.auth_mode, v => laneSet(name, 'auth_mode', v), { options: [['bearer', 'API Key'], ['none', '本地免 Key']] })),
          value.auth_mode === 'bearer' && h('div', { style: { marginTop: 17 } }, field('API Key（留空保留已存密钥）', value.api_key, v => laneSet(name, 'api_key', v), {
            type: 'password', display: 'API Key', placeholder: value.api_key_configured ? '已安全保存 · 留空保留' : '输入此供应商的 API Key', hint: '密钥只保存在当前实例，不会回显或写入聊天。' })),
          value.auth_mode === 'none' && h('p', { className: 'bqs-hint', style: { marginTop: 12 } }, '免 Key 仅用于此设备上的本地回环模型服务。'),
          disclosure('模型能力与预算', h(React.Fragment, {}, h('div', { className: 'bqs-grid' },
            field('已确认的上下文上限', value.context_window, v => laneSet(name, 'context_window', v), { type: 'number', display: '上下文上限', hint: '以供应商或本地服务的实际能力为准。' }),
            field('输出预算', value.max_tokens, v => laneSet(name, 'max_tokens', v), { type: 'number', hint: '单次回复的最大 Token 数。' }),
            field('思考强度（可留空）', value.reasoning_effort || '', v => laneSet(name, 'reasoning_effort', v), { display: '思考强度', options: [
              ['', '模型默认'], ['off', '关闭'], ['minimal', '最小'], ['low', '低'], ['medium', '中'], ['high', '高'], ['xhigh', '更高'], ['max', '最高']] })),
            toggle('图片理解', value.vision, v => laneSet(name, 'vision', v), { aria: '已确认此模型支持图片', hint: '仅在确认当前模型支持图片时开启。' }),
            field('JSON 映射', value.mappingText, v => laneSet(name, 'mappingText', v), { display: '思考档位映射', code: true, hint: '高级选项。供应商明确要求时填写 JSON，否则保留 {}。' })),
          `${Math.round(value.context_window / 1024)}K 上下文 · ${Math.round(value.max_tokens / 1024)}K 输出`)), {
            caption: character ? '负责与你对话、表达角色和组织记忆。' : '负责调用工具、执行任务，并把真实结果交回角色脑。',
            action: button('读取模型列表', async () => { const result = await call('models', { lane: name }); setNotice('可用模型：' + result.models.join('、')); }, {
              aria: '读取已保存模型列表（不推理）', variant: 'link', glyph: 'refresh', disabled: !sample.configured }),
          });
      };
      const save = () => run(async () => {
        const models = {};
        for (const lane of modelProfile ? [] : draft.action_uses_character ? ['character'] : ['character', 'action']) {
          const { mappingText, ...model } = draft.models[lane];
          try { model.reasoning_efforts = JSON.parse(mappingText || '{}'); } catch { throw Error('思考档位映射须为有效 JSON'); }
          models[lane] = model;
        }
        const changes = { ...draft, models }; if (modelProfile) delete changes.models;
        const accepted = await call('save', { revision: sample.config.revision, changes, persona: text, persona_digest: sample.persona.digest,
          ...(modelProfile ? { use_model_profile: modelProfile } : {}), ...(saveProfileName.trim() ? { save_model_profile: saveProfileName.trim() } : {}) });
        setSample(old => ({ ...old, operation: accepted })); setNotice('配置已排队；空闲后应用，原生 DSH 会自动重连。');
      });
      const modelsPanel = () => h(React.Fragment, {},
        Object.keys(sample.config.model_profiles || {}).length > 0 && field('供应商 / 模型方案', modelProfile, setModelProfile, {
          display: '使用已存方案', options: [['', '手动编辑当前配置'], ...Object.keys(sample.config.model_profiles).map(name => [name, name])] }),
        modelProfile ? card('已选择模型方案', h('div', { className: 'bqs-shared', style: { marginTop: 0 } }, icon('folder'),
          h('div', {}, h('p', {}, modelProfile), h('span', { className: 'bqs-hint' }, '应用时复用方案中的两个脑和私有凭据，密钥不回显。'))))
          : h(React.Fragment, {}, lane('character'), card('双脑协作', h(React.Fragment, {},
            toggle('行动脑复用角色脑模型', draft.action_uses_character, v => set('action_uses_character', v), {
              aria: '行动脑复用角色脑的供应商和模型（会话与职责仍独立）', hint: '同一个模型，两份独立的会话与职责。关闭后可单独配置行动脑。' }),
            draft.action_uses_character && h('div', { className: 'bqs-shared' }, icon('link'), h('div', {},
              h('div', { className: 'bqs-row' }, pill('角色脑', 'purple'), icon('arrow', 13), pill('行动脑', 'blue')),
              h('span', { className: 'bqs-hint', style: { marginTop: 5 } }, draft.models.character.name || '配置角色脑后，行动脑自动复用其供应商和模型。'))))),
          !draft.action_uses_character && lane('action')),
        card('方案与权限', h('div', { className: 'bqs-grid' },
          field('随本次应用另存模型方案（可留空）', saveProfileName, setSaveProfileName, { display: '另存为模型方案', placeholder: '例如：日常对话', hint: '可选。下次可直接切换，无需重复填写。' }),
          field('主机工具权限', draft.host_permission_mode, v => set('host_permission_mode', v), { options: [
            ['read-only', '只读'], ['workspace-write', '工作目录写入'], ['danger-full-access', '完整当前用户权限（高风险）']], hint: '只授予你确实需要的权限。' })), { glyph: 'shield' }));
      const personaPanel = () => h(React.Fragment, {},
        card('角色身份', h('div', { className: 'bqs-grid' },
          field('角色名（由你自取）', draft.character_name, v => set('character_name', v), { display: '怎么称呼你的 Bot', placeholder: 'Bot', hint: '名字、性格和背景，都由你来决定。' }),
          h('div', { className: 'bqs-row', style: { alignSelf: 'center', paddingLeft: 6 } },
            h('span', { className: 'bqs-persona-preview', 'aria-hidden': true }, Array.from(draft.character_name.trim() || 'B')[0]),
            h('div', {}, h('p', { style: { fontWeight: 500 } }, draft.character_name.trim() || 'Bot'), h('span', { className: 'bqs-hint' }, '你的角色 · 没有预设人物'))))),
        card('人格与表达', h(React.Fragment, {},
          h('div', { className: 'bqs-editor-head' }, h('span', { className: 'bqs-editor-meta' }, 'MARKDOWN'),
            h('label', { className: 'bqs-button bqs-import', 'data-variant': 'ghost' }, icon('upload', 15), '导入文件',
              h('input', { type: 'file', 'aria-label': '导入 Markdown 人格', accept: '.md,text/markdown,text/plain', onChange: e => run(async () => {
                const file = e.target.files[0]; if (!file) { setNotice(''); return; }
                if (file.size > 256 * 1024) throw Error('人格文件不能超过 256 KiB。');
                setText(await file.text()); setNotice('文件已载入编辑器；保存应用后才会替换当前人格。');
              }) }))),
          h('textarea', { className: 'bqs-control bqs-textarea', 'aria-label': '人格正文', rows: 11, value: text, spellCheck: false, onChange: e => setText(e.target.value) }),
          h('div', { className: 'bqs-row-between', style: { marginTop: 10 } }, h('span', { className: 'bqs-hint' }, '描述性格、语气、背景，以及希望它如何与你相处。'),
            h('span', { className: 'bqs-editor-meta' }, `${text.length.toLocaleString()} 字符`))), {
            caption: '用自然语言写就好，也可以导入已有的 Markdown 人格。',
            tail: h('span', { className: 'bqs-row' }, icon('shield', 14), '切换人格不会删除聊天历史。'),
          }),
        card('人格预设', h('div', { className: 'bqs-stack' },
          sample.persona.presets.length > 0 && h(React.Fragment, {},
            field('人格预设', personaPreset, setPersonaPreset, { display: '使用已存预设', options: [['', '选择一个人格'], ...sample.persona.presets.map(name => [name, name])] }),
            h('div', {}, button('加载到编辑器', async () => { const value = await call('preset', { operation: 'read', name: personaPreset }); setText(value.text); setNotice('已加载草稿；保存应用后才替换当前人格。'); }, {
              aria: '加载人格预设到编辑器', disabled: !personaPreset, glyph: 'folder' }))),
          field('另存人格预设名称', savePersonaName, setSavePersonaName, { display: '将当前草稿另存为', placeholder: '给这份人格起个名字', hint: '支持字母、汉字、数字、下划线和连字符。' }),
          h('div', {}, button('保存为人格预设', async () => {
            const result = await call('preset', { operation: 'save', name: savePersonaName, text });
            setSample(old => ({ ...old, persona: { ...old.persona, presets: result.presets } })); setNotice('人格预设已保存；当前角色未切换。');
          }, { aria: '仅保存人格预设（不改当前角色）', disabled: !savePersonaName, variant: 'soft', glyph: 'save' }))), { glyph: 'folder' }));
      const qqPanel = () => {
        const running = sample.status.services.napcat.running, channel = sample.status.gateway?.state || sample.status.services.gateway.state;
        const stateLabel = ({ disabled: '未启用', stopped: '未连接', connected: '最近心跳正常', connecting: '正在连接', stale: '心跳已过期', disconnected: '已断开' })[channel] || '尚未确认';
        return h(React.Fragment, {}, h('section', { className: 'bqs-card' }, h('div', { className: 'bqs-card-body' },
          h('div', { className: 'bqs-row-between' }, h('div', { className: 'bqs-app' }, h('div', { className: 'bqs-app-icon' }, icon('plug', 24)),
            h('div', {}, h('h3', {}, 'NapCat'), h('p', {}, sample.napcat.installed ? '已随预构建包提供' : '当前实例尚未装配'))),
            pill(sample.napcat.version ? 'v' + sample.napcat.version : '未安装', 'blue')),
          h('div', { className: 'bqs-status-grid' },
            h('div', { className: 'bqs-status-cell' }, h('span', {}, 'NAPCAT 进程'), h('span', { className: 'bqs-status-value' }, h('span', { className: 'bqs-dot' }), running ? '已启动' : '未启动')),
            h('div', { className: 'bqs-status-cell' }, h('span', {}, 'QQ 连接'), h('span', { className: 'bqs-status-value' }, h('span', { className: 'bqs-dot' }), stateLabel))),
          sample.napcat.launch_hint && h('p', { className: 'bqs-hint', style: { marginBottom: 14 } }, sample.napcat.launch_hint),
          h('div', { className: 'bqs-row' }, button(running ? '重启 NapCat' : '启动 NapCat', async () => {
            await call('napcat', { operation: running ? 'restart' : 'start' }); await load(); setNotice('启动请求已接纳；请到管理页面核对状态并自行扫码登录。');
          }, { aria: running ? '重启本实例 NapCat' : '启动 NapCat', disabled: !sample.napcat.launch_ready, variant: 'soft', glyph: running ? 'refresh' : 'play' }),
          h('a', { className: 'bqs-button', href: sample.napcat.webui_url, target: '_blank', rel: 'noopener noreferrer', 'aria-label': '打开 NapCat 管理页面 ↗' }, '打开管理页面', icon('external', 14))),
          h('div', { style: { marginTop: 10 } }, button('复制管理密码', async () => {
            const value = await call('napcat', { operation: 'webui-key' }); if (!value.key) throw Error('此实例尚无管理密码');
            await navigator.clipboard.writeText(value.key); setNotice('NapCat 管理密码已复制，不会放入 URL 或日志。');
          }, { aria: '复制 NapCat 管理密码', disabled: !sample.napcat.installed, variant: 'ghost', glyph: 'key' }))),
          h('div', { className: 'bqs-card-tail' }, '扫码登录由你完成。不会关闭普通 QQ，也不会自动替你登录。')),
          card('连接你的 QQ', h('div', { className: 'bqs-stack' },
            h('div', { className: 'bqs-steps' }, ...['扫码登录', '选择账号', '保存并启用'].map((name, i) => h(React.Fragment, { key: name },
              i > 0 && h('span', { className: 'bqs-step-line', 'aria-hidden': true }, '—'), h('span', { className: 'bqs-step' }, h('b', {}, i + 1), name)))),
            sample.napcat.accounts.length === 0 ? h('div', { className: 'bqs-empty' }, '还没有发现账号。先在 NapCat 管理页面登录，再刷新列表。') :
              field('NapCat 账号', account, setAccount, { display: '选择已登录账号', options: sample.napcat.accounts.map(row => [row.account_id, row.account_id]) }),
            h('div', { className: 'bqs-row' }, button('刷新账号', async () => { const value = await load(); setAccount(value.napcat.accounts[0]?.account_id || ''); setNotice('账号列表已读取，不包含 Token。'); }, {
              aria: '刷新已登录账号', glyph: 'refresh' }),
            button('配置本机连接', async () => { await call('napcat', { operation: 'link', account_id: account, revision: sample.config.revision }); await load(true);
              setNotice('连接参数已配置。请重启本实例 NapCat，填写 Owner QQ 并勾选启用 QQ，最后保存应用。');
            }, { aria: '配置此账号的本机连接', disabled: !account || !sample.configured, glyph: 'link' })),
            field('Owner QQ（逗号分隔）', (draft.onebot.admin_ids || []).join(','), v => onebotSet('admin_ids', v.split(',').map(x => x.trim()).filter(Boolean)), {
              display: 'Owner QQ', placeholder: '填写你的 QQ 号', hint: '多个账号用英文逗号分隔。只有明确指定的 Owner 才有管理权限。' }),
            toggle('启用 QQ 接入', draft.onebot.enabled, v => onebotSet('enabled', v), { aria: '显式启用 QQ 接入', hint: '默认关闭。不接 QQ，也可以完整使用 Web 对话。' }),
            disclosure('外部 NapCat / 手动连接参数', h(React.Fragment, {},
              field('Bot QQ', draft.onebot.account_id, v => onebotSet('account_id', v), { placeholder: 'Bot 登录的 QQ 号' }),
              field('OneBot HTTP URL（本机回环）', draft.onebot.http_url, v => onebotSet('http_url', v), { display: 'OneBot HTTP 地址', code: true, placeholder: 'http://127.0.0.1:3000' }),
              field('OneBot WebSocket URL（本机回环）', draft.onebot.ws_url, v => onebotSet('ws_url', v), { display: 'OneBot WebSocket 地址', code: true, placeholder: 'ws://127.0.0.1:3001' }),
              field('OneBot Token（留空保留）', draft.onebot.token, v => onebotSet('token', v), { display: 'OneBot Token', type: 'password', placeholder: '留空保留已存 Token' }))),
            h('div', { className: 'bqs-row' }, button('重新连接', async () => { await call('napcat', { operation: 'connect' }); await load(); setNotice('已核对账号并请求连接，请核对新鲜心跳。'); }, {
              aria: '重新连接 QQ', disabled: !sample.config.onebot.enabled, glyph: 'refresh' }),
            button('断开连接', async () => { await call('napcat', { operation: 'disconnect' }); await load(); setNotice('已断开本实例 QQ 通道，保留 NapCat 登录。'); }, {
              aria: '断开 QQ（保留登录）', variant: 'ghost', disabled: !sample.status.services.gateway.running }))), {
                caption: '完成账号配置后，重启本实例 NapCat，再保存并应用。',
              }));
      };
      const dirty = draft && baseline.current !== JSON.stringify({ draft, text, modelProfile, saveProfileName });
      const active = TABS.find(item => item.id === tab);
      return h(React.Fragment, {}, h('style', {}, STYLES),
        h('div', { className: 'bqs-page' },
          h('header', { className: 'bqs-top' },
            h('div', { className: 'bqs-mark' }, icon(active.icon, 21)),
            h('div', {}, h('div', { className: 'bqs-top-title' }, active.label), h('p', { className: 'bqs-top-caption' }, active.description)),
            h('div', { className: 'bqs-top-end' }, h('span', { className: 'bqs-state', 'data-state': dirty ? 'dirty' : sample?.configured ? 'ready' : 'new' },
              h('span', { className: 'bqs-dot' }), pending ? '等待应用' : dirty ? '有未保存更改' : sample?.configured ? '配置已保存' : '待完成配置'))),
          h('form', { className: 'bqs-form', onSubmit: event => { event.preventDefault(); save(); } },
            h('div', { ref: scroll, className: 'bqs-scroll' },
              notice && h('div', { className: 'bqs-notice', role: 'status', 'aria-live': 'polite', 'data-kind': noticeKind }, icon('info', 15), h('span', {}, notice)),
              !draft ? h('div', { className: 'bqs-skeleton', 'aria-label': '正在读取私有配置', 'aria-busy': true }, h('span'), h('span'),
                button('重新读取', async () => { await load(true); setNotice(''); }, { glyph: 'refresh' })) :
                h('fieldset', { className: 'bqs-fields', disabled: busy || pending, 'aria-label': active.label + '配置' }, tab === 'models' ? modelsPanel() : tab === 'persona' ? personaPanel() : qqPanel())),
            h('footer', { className: 'bqs-footer' }, h('span', { className: 'bqs-footer-note' }, icon('shield', 13), '只保存在当前实例'),
              button('重新读取', async () => { await load(true); setNotice('已重新读取。'); }, { aria: '重新读取（放弃未保存编辑）', variant: 'ghost', glyph: 'refresh' }),
              h('button', { type: 'submit', className: 'bqs-button', 'data-variant': 'primary', disabled: !draft || busy || pending },
                pending ? icon('refresh', 15) : icon('check', 16), pending ? '等待应用 / 重连…' : '保存并应用配置')))));
    }
    return {
      inject: ['slots', 'connection'],
      apply(ctx) {
        setupConnection = ctx.connection;
        const pages = [
          ['soyo-bot-models', 30, '模型与脑区', 'models'],
          ['soyo-bot-persona', 31, '角色设定', 'persona'],
          ['soyo-bot-qq', 32, 'NapCat / QQ', 'qq'],
        ];
        for (const [id, order, label, pageTab] of pages) {
          const Page = () => React.createElement(NativeSetup, { pageTab });
          ctx.slots.inject('settings.section', () => ctx.slots.register({ name: 'settings.section', id, order, label }, Page));
        }
        const publicURL = window.__SOYO_DASHBOARD_URL__;
        const managementURL = publicURL ? new URL(publicURL) : null;
        if (managementURL && (!['http:', 'https:'].includes(managementURL.protocol) || managementURL.username || managementURL.password || managementURL.search || managementURL.hash || managementURL.pathname !== '/')) throw new Error('Dashboard browser URL must be clean.');
        const callSetup = async (method, request) => {
          const result = await setupConnection.rpc.call('/api', 'botSetup/' + method, { args: request === undefined ? {} : { request } });
          if (!result.ok) throw Error(result.error?.message || '管理操作未完成');
          return result.value;
        };
        const ManagementPage = () => {
          const [status, setStatus] = React.useState(null);
          const [service, setService] = React.useState('manager');
          const [lines, setLines] = React.useState([]);
          const [notice, setNotice] = React.useState('');
          const [busy, setBusy] = React.useState(false);
          const refresh = async () => {
            const next = await callSetup('status');
            setStatus(next);
            const log = await callSetup('logs', { service });
            setLines(log.lines || []);
          };
          React.useEffect(() => { refresh().catch(error => setNotice(error.message)); }, []);
          React.useEffect(() => {
            const timer = setInterval(() => { callSetup('logs', { service }).then(value => setLines(value.lines || [])).catch(() => {}); }, 2500);
            return () => clearInterval(timer);
          }, [service]);
          const control = async (operation, name) => {
            setBusy(true); setNotice('');
            try { await callSetup('service', { operation, service: name }); await refresh(); setNotice('操作已提交；请核对状态与日志。'); }
            catch (error) { setNotice(error.message); } finally { setBusy(false); }
          };
          const stateText = (name, row) => name === 'gateway'
            ? ({ disabled: '未启用', stopped: '未连接', connected: '最近心跳正常', connecting: '正在连接', stale: '心跳已过期', disconnected: '已断开' })[row.state] || '尚未确认'
            : row.running ? '运行中' : '未运行';
          return h(React.Fragment, {}, h('style', {}, STYLES),
            h('div', { className: 'bqs-page' },
              h('header', { className: 'bqs-top' },
                h('div', { className: 'bqs-mark' }, icon('external', 21)),
                h('div', {}, h('div', { className: 'bqs-top-title' }, '管理 Web'),
                  h('p', { className: 'bqs-top-caption' }, '本实例的服务状态、启停与运行日志'))),
              h('div', { className: 'bqs-scroll' },
                notice && h('div', { className: 'bqs-notice', 'data-kind': 'error', role: 'status', 'aria-live': 'polite' }, icon('info', 15), h('span', {}, notice)),
                h('section', { className: 'bqs-card' },
                  h('div', { className: 'bqs-card-head' }, h('h3', { className: 'bqs-card-title' }, icon('layers', 16), '服务')),
                  h('div', { className: 'bqs-card-body' },
                    status ? Object.entries(status.services).map(([name, row]) => h('div', { className: 'bqs-service-row', key: name },
                      h('div', {}, h('span', { className: 'bqs-service-name' }, name),
                        h('span', { className: 'bqs-hint' }, stateText(name, row) + (row.pid ? ' · PID ' + row.pid : ''))),
                      ['napcat', 'live2d'].includes(name) && h('button', { type: 'button', className: 'bqs-button', 'data-variant': 'soft', disabled: busy,
                        onClick: () => control(row.running ? 'stop' : 'start', name) }, row.running ? '停止' : '启动'))) :
                      h('div', { className: 'bqs-skeleton' }, h('span'), h('span'))),
                  h('div', { className: 'bqs-card-tail' }, h('div', { className: 'bqs-row' },
                    h('button', { type: 'button', className: 'bqs-button', 'data-variant': 'primary', disabled: busy,
                      onClick: () => control('start', 'native') }, icon('play', 14), '启动原生 Web'),
                    h('button', { type: 'button', className: 'bqs-button', 'data-variant': 'ghost', disabled: busy,
                      onClick: () => control('stop', 'native') }, '停止原生服务')))),
                h('section', { className: 'bqs-card' },
                  h('div', { className: 'bqs-card-head' }, h('h3', { className: 'bqs-card-title' }, icon('info', 16), '运行日志'),
                    h('div', { className: 'bqs-head-action' }, h('label', { className: 'bqs-select' },
                      h('select', { className: 'bqs-control', 'aria-label': '日志服务', value: service, onChange: event => setService(event.target.value) },
                        ...['manager', 'web', 'gateway', 'napcat', 'live2d'].map(name => h('option', { key: name, value: name }, name))), icon('down', 14)))),
                  h('div', { className: 'bqs-card-body' },
                    h('pre', { className: 'bqs-logs' }, lines.length ? lines.join('\n') : '暂无日志。'),
                    h('p', { className: 'bqs-hint' }, '密钥会脱敏。回合结束不等于 QQ 已发送，以通道真实回执为准。')),
                  h('div', { className: 'bqs-card-tail' }, h('div', { className: 'bqs-row' },
                    h('button', { type: 'button', className: 'bqs-button', 'data-variant': 'ghost',
                      onClick: () => refresh().catch(error => setNotice(error.message)) }, icon('refresh', 14), '刷新'),
                    managementURL && h('a', { className: 'bqs-button', 'data-variant': 'ghost', href: managementURL.origin, target: '_blank', rel: 'noopener noreferrer' },
                      '打开独立管理 Web ↗', icon('external', 14))))))));
        };
        ctx.slots.inject('settings.section', () => ctx.slots.register({ name: 'settings.section', id: 'soyo-dashboard', order: 34, label: '管理 Web' }, ManagementPage));
      },
    };
  },
});
