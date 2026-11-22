"""Processo de uma requisição no namespace do contêiner pessoal."""

import base64
import json
import sys

from file_service import FileError, LinuxFileService


def main():
    request = json.loads(sys.stdin.buffer.read(12 * 1024 * 1024))
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
    print(json.dumps({'data': result}, separators=(',', ':')))


if __name__ == '__main__':
    try:
        main()
    except (FileError, KeyError, ValueError) as exc:
        print(json.dumps({'error': getattr(exc, 'code', 'INVALID_REQUEST')}))
        sys.exit(2)
