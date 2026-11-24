"""Processo de uma requisição no namespace do contêiner pessoal."""

import base64
import json
import sys
import re
import threading
from types import SimpleNamespace

from file_service import FileError, LinuxFileService
from workspace_files import WorkspaceError, WorkspaceFiles
from git_workspace import GitError, GitWorkspace


def error_code(exc):
    if isinstance(exc, (WorkspaceError, GitError)) and re.fullmatch(r'[A-Z][A-Z0-9_]{1,63}', str(exc)):
        return str(exc)
    return getattr(exc, 'code', 'INVALID_REQUEST')


def workspace_execute(request):
    operation = request['operation']
    owner = request['account_id']
    actor = SimpleNamespace(account_id=owner)
    authorize = lambda _actor, _capability: None
    active = lambda _actor: True
    files = WorkspaceFiles('/persist', owner, authorize, active)
    if operation == 'ws_tree':
        budget = [1000]
        def walk(relative='', depth=0):
            cursor = 0
            result = []
            while budget[0] and depth < 8:
                page = files.list_tree(actor, relative, cursor, min(200, budget[0]))
                for entry in page['entries']:
                    if entry['kind'] == 'link':
                        continue
                    path = f"{relative}/{entry['name']}".lstrip('/')
                    node = {'path': path, 'name': entry['name'], 'kind': entry['kind']}
                    budget[0] -= 1
                    if entry['kind'] == 'directory' and budget[0] and depth < 7:
                        node['children'] = walk(path, depth + 1)
                    result.append(node)
                    if not budget[0]:
                        break
                if page['next_cursor'] is None or not budget[0]:
                    break
                cursor = page['next_cursor']
            return result
        return walk()
    if operation == 'ws_read':
        return files.read(actor, request['path'])
    if operation == 'ws_write':
        return {'revision': files.write(actor, request['path'], request['content'], request['revision'])}
    if operation == 'ws_search':
        return files.search(actor, request['query'], threading.Event())
    git = GitWorkspace('/persist', owner, authorize, active)
    if operation == 'ws_git_status':
        return {'branch': git._run('branch', '--show-current').strip(),
                'entries': git.status(actor)}
    if operation == 'ws_git_diff':
        return {'text': git.diff(actor, request['path'])}
    if operation == 'ws_git_stage':
        git.stage(actor, request['paths'])
        return {'ok': True}
    if operation == 'ws_git_commit':
        return {'hash': git.commit(actor, request['message'], request['author_name'],
                                   request['author_email'])}
    raise WorkspaceError('INVALID_OPERATION')


def execute(request):
    if not isinstance(request, dict) or not isinstance(request.get('operation'), str):
        raise ValueError('INVALID_REQUEST')
    if request['operation'].startswith('ws_'):
        return {'data': workspace_execute(request)}
    with LinuxFileService('/') as files:
        operation = request['operation']
        path = request.get('path', '/')
        if operation == 'list':
            result = files.list(path)
        elif operation == 'metadata':
            result = files.metadata(path)
        elif operation == 'read':
            data, revision = files.read(path)
            result = {'content': base64.b64encode(data).decode(), 'revision': revision}
        elif operation == 'write':
            data = base64.b64decode(request['content'], validate=True)
            result = {'revision': files.write(path, data, request.get('revision'), request.get('replace', False))}
        elif operation == 'mkdir':
            files.mkdir(path)
            result = {'created': True}
        elif operation == 'move':
            files.move(path, request['destination'])
            result = {'moved': True}
        elif operation == 'copy':
            files.copy(path, request['destination'])
            result = {'copied': True}
        elif operation == 'delete':
            files.delete(path)
            result = {'deleted': True}
        else:
            raise FileError('INVALID_OPERATION')
    return {'data': result}


def respond(request):
    try:
        return execute(request)
    except (FileError, WorkspaceError, GitError, KeyError, ValueError, TypeError) as exc:
        return {'error': error_code(exc)}


def main():
    if len(sys.argv) == 2 and sys.argv[1] == '--serve':
        while line := sys.stdin.buffer.readline(12 * 1024 * 1024 + 2):
            if len(line) > 12 * 1024 * 1024 + 1 or not line.endswith(b'\n'):
                break
            try:
                response = respond(json.loads(line))
            except ValueError:
                response = {'error': 'INVALID_REQUEST'}
            sys.stdout.buffer.write(json.dumps(response, separators=(',', ':')).encode() + b'\n')
            sys.stdout.buffer.flush()
        return
    if len(sys.argv) != 1:
        raise ValueError('INVALID_REQUEST')
    request = json.loads(sys.stdin.buffer.read(12 * 1024 * 1024))
    response = respond(request)
    print(json.dumps(response, separators=(',', ':')))
    if 'error' in response:
        sys.exit(2)


if __name__ == '__main__':
    try:
        main()
    except (FileError, WorkspaceError, GitError, KeyError, ValueError, TypeError) as exc:
        print(json.dumps({'error': error_code(exc)}))
        sys.exit(2)
