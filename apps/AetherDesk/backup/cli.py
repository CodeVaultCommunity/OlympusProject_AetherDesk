"""Operação offline de backup e restauração: python -m apps.AetherDesk.backup.cli."""

import argparse
import os
from pathlib import Path

from apps.AetherDesk.administration.service import AdministrationService
from apps.AetherDesk.backup.service import BackupService, restore_snapshot, verify_snapshot
from apps.AetherDesk.composition.app import AppComposition
from apps.AetherDesk.identity import IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker


def main():
    parser = argparse.ArgumentParser(description='Backup e restauração do AetherDesk')
    sub = parser.add_subparsers(dest='command', required=True)
    run = sub.add_parser('run-now')
    run.add_argument('--destination', type=Path, required=True)
    run.add_argument('--retention', choices=['replace', 'days'], default='replace')
    run.add_argument('--days', type=int)
    verify = sub.add_parser('verify')
    verify.add_argument('snapshot', type=Path)
    restore = sub.add_parser('restore')
    restore.add_argument('snapshot', type=Path)
    restore.add_argument('--data-dir', type=Path, required=True)
    restore.add_argument('--confirm-offline', action='store_true')
    args = parser.parse_args()
    if args.command == 'verify':
        manifest = verify_snapshot(args.snapshot)
        print(f"Snapshot verificado: {len(manifest['volumes'])} volumes")
        return
    image = os.environ.get('AETHERDESK_RUNTIME_IMAGE', 'aetherdesk-files:w003')
    runtime = DockerEnvironmentBroker(image)
    if args.command == 'restore':
        if not args.confirm_offline:
            parser.error('Pare o serviço e use --confirm-offline para restaurar')
        manifest = restore_snapshot(args.snapshot, args.data_dir, runtime)
        print(f"Restauração concluída: {len(manifest['volumes'])} volumes")
        return
    secret = os.environ.get('AETHERDESK_BOOTSTRAP_TOKEN', '')
    data_dir = Path(os.environ.get('AETHERDESK_DATA_DIR', '/var/lib/aetherdesk'))
    identity = IdentityService(data_dir / 'identity.sqlite3', secret)
    admin = AdministrationService(data_dir / 'identity.sqlite3', identity,
                                  AppComposition(identity, runtime))
    backup = BackupService(data_dir, admin, runtime)
    result = backup.run_once(args.destination, args.retention, args.days)
    print(f'Snapshot criado: {result}')


if __name__ == '__main__':
    main()
