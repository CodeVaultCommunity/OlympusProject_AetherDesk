"""Ensaio descartável do agente W005 em contêiner sem rede."""

import base64
import json
import subprocess
import uuid


def run(*args, data=None):
    result = subprocess.run(['docker', *args], input=data, capture_output=True, timeout=90)
    if result.returncode:
        raise RuntimeError(f'docker {args[0]} falhou: {result.stderr.decode("utf-8", "replace")[:500]}')
    return result.stdout.decode('utf-8', 'replace').strip()


def main():
    suffix = uuid.uuid4().hex
    volume = 'aetherdesk-w005-agent-v-' + suffix
    container = 'aetherdesk-w005-agent-c-' + suffix
    account = str(uuid.uuid4())
    created = False
    started = False
    try:
        run('volume', 'create', volume)
        created = True
        run('run', '--detach', '--name', container, '--network', 'none', '--read-only',
            '--cap-drop', 'ALL', '--security-opt', 'no-new-privileges',
            '--mount', f'type=volume,source={volume},target=/persist',
            'aetherdesk-files:w005-local')
        started = True

        def agent(payload):
            result = subprocess.run(['docker', 'exec', '-i', '--user', '10001:10001', container,
                                     'python3', '/opt/aetherdesk/file_agent.py'],
                                    input=json.dumps(payload, separators=(',', ':')).encode(),
                                    capture_output=True, timeout=30)
            if result.returncode not in (0, 2):
                raise RuntimeError('Agent indisponível')
            return json.loads(result.stdout)

        encoded = base64.b64encode(b'print(1)\n').decode()
        assert agent({'operation': 'write', 'path': '/persist/main.py',
                      'content': encoded, 'replace': False})['data']['revision']
        tree = agent({'operation': 'ws_tree', 'account_id': account})['data']
        assert any(item['name'] == 'main.py' for item in tree), tree
        read = agent({'operation': 'ws_read', 'account_id': account, 'path': 'main.py'})['data']
        assert read['text'] == 'print(1)\n', read
        assert agent({'operation': 'ws_write', 'account_id': account, 'path': 'main.py',
                      'content': 'print(2)\n', 'revision': read['revision']})['data']['revision']
        assert agent({'operation': 'ws_search', 'account_id': account,
                      'query': 'print(2)'})['data']['matches'][0]['path'] == 'main.py'
        stale = agent({'operation': 'ws_write', 'account_id': account, 'path': 'main.py',
                       'content': 'stale', 'revision': read['revision']})
        assert stale.get('error') == 'STALE_REVISION', stale
        run('exec', '--user', '10001:10001', container, 'git', '-C', '/persist', 'init', '-q')
        status = agent({'operation': 'ws_git_status', 'account_id': account})['data']
        assert any(item['path'] == 'main.py' for item in status['entries']), status
        assert agent({'operation': 'ws_git_stage', 'account_id': account,
                      'paths': ['main.py']})['data']['ok']
        committed = agent({'operation': 'ws_git_commit', 'account_id': account,
                           'message': 'fixture', 'author_name': 'Fixture',
                           'author_email': 'fixture@aetherdesk.local'})['data']['hash']
        assert len(committed) == 40, committed
        print(json.dumps({'ok': True, 'tree': len(tree), 'commit': committed,
                          'network': 'none', 'image': 'aetherdesk-files:w005-local'}))
    finally:
        if started:
            subprocess.run(['docker', 'rm', '-f', container], capture_output=True, timeout=30)
        if created:
            subprocess.run(['docker', 'volume', 'rm', volume], capture_output=True, timeout=30)


if __name__ == '__main__':
    main()
