"""Bootstrap local sem enviar a senha inicial pelo shell ou por HTTP."""

import argparse
import getpass
import os
from pathlib import Path

from .service import IdentityService


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('command', choices=['bootstrap'])
    parser.add_argument('--username', required=True)
    args = parser.parse_args()
    password = getpass.getpass('Senha inicial do administrador: ')
    confirmation = getpass.getpass('Repita a senha: ')
    if password != confirmation:
        parser.error('Senhas diferentes')
    service = IdentityService(Path(os.environ.get('AETHERDESK_DATA_DIR', '/var/lib/aetherdesk')) /
                              'identity.sqlite3', os.environ.get('AETHERDESK_BOOTSTRAP_TOKEN', ''))
    print('Administrador criado:', service.bootstrap(os.environ['AETHERDESK_BOOTSTRAP_TOKEN'],
                                                     args.username, password))


if __name__ == '__main__':
    main()
