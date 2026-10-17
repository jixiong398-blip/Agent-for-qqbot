# SPDX-License-Identifier: MIT
"""Actual authenticated DSH browser -> action entry/native history/notes pane.

Read-only except the explicit reveal action restores native archive visibility;
it never resumes the child, submits a prompt or sends QQ. Private key stays in
the login form, never argv, URL, evidence or output.
"""
import argparse
import json
import os
import uuid
from pathlib import Path

import httpx
import yaml
from playwright.sync_api import sync_playwright


class Loader(yaml.SafeLoader):
    pass


Loader.add_constructor('tag:yaml.org,2002:js', lambda loader, node: loader.construct_scalar(node))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--chromium', type=Path, required=True)
    parser.add_argument('--evidence', type=Path, required=True)
    args = parser.parse_args()
    home = args.config.parent
    rows = yaml.load((home / 'profiles/soyo-web/cordis.patch.yml').read_text(), Loader=Loader)
    boundary = next(row['config'] for item in rows for row in [item, *item.get('insert', [])] if row.get('id') == 'soyo-host-boundary')
    base = 'http://' + boundary['host'] + ':' + str(boundary['port'])
    key = Path(boundary['accessKeyFile']).read_text().strip()
    proof = {'status': 'unverified', 'model_requests': 0, 'qq_sends': 0}
    try:
        with httpx.Client(base_url=base, trust_env=False, timeout=30) as client:
            assert client.post('/soyo-login', data={'key': key}, headers={'Origin': base}).status_code == 303
            def rpc(method, args):
                value = client.post('/api/' + method, json={'type': 'client-request', 'rpcId': str(uuid.uuid4()),
                    'method': method, 'payload': {'args': args}}, headers={'Origin': base}).raise_for_status().json()
                assert value['result']['ok'], value['result'].get('error')
                return value['result']['value']
            catalog = rpc('soyoBrains/catalog', {})
            action = next(task for task in catalog['tasks'] if task.get('native_address') and
                          any(row.get('commit') for row in task['evidence']))
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=str(args.chromium), args=['--no-sandbox'])
            try:
                page = browser.new_page(viewport={'width': 1440, 'height': 1000})
                page.set_default_timeout(60000)
                page.goto(base)
                page.get_by_label('DSH 访问密钥').fill(key)
                page.get_by_role('button', name='进入 DSH 原生面板').click()
                entry = page.get_by_label('Soyo 行动会话入口')
                entry.wait_for()
                entry.locator('summary').click()
                action_button = entry.get_by_role('button', name='行动会话 ' + action['id'], exact=True)
                action_button.wait_for()
                action_button.click()
                page.wait_for_function("needle => document.body?.innerText.includes(needle)", arg=action['objective'][:40])
                # Viewing the official native history, not only our task card.
                page.get_by_text('normalize_reply_lines', exact=False).first.wait_for()
                proof.update(action_entry_visible=True, native_child_opened=True, child_session_id=action['child_session_id'])
                # The right sidebar guide opens a supported native pane.
                entry.get_by_role('button', name='跨会话便签', exact=True).click()
                panel = page.get_by_label('Soyo 跨会话便签')
                panel.wait_for()
                panel.get_by_role('combobox').wait_for()
                page.wait_for_function("document.querySelector('[aria-label=\"Soyo 跨会话便签\"] select')?.options.length > 1")
                assert panel.get_by_role('combobox').locator('option').count() > 1
                panel.locator('details').first.wait_for()
                assert not panel.get_by_role('alert').count()
                proof.update(notes_pane_visible=True, notes_catalog_rendered=True, persisted_notes_rendered=True,
                             action_ledger_tasks=len(catalog['tasks']), status='verified')
            finally:
                browser.close()
    except BaseException as error:
        proof['error'] = str(error).replace(base, '<dsh-origin>')[:1600]
        raise
    finally:
        fd = os.open(args.evidence, os.O_CREAT | os.O_WRONLY | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w') as file:
            json.dump(proof, file, ensure_ascii=False, indent=2)
        print(json.dumps(proof, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
