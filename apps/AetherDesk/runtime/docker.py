"""Broker local para ambientes pessoais. IDs vêm do serviço, nunca do navegador."""

from __future__ import annotations

import re
import subprocess
import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Sequence


class RuntimeError(Exception):
    def __init__(self, code: str, detail: str = ""):
        self.code = code
        super().__init__(detail or code)


@dataclass(frozen=True)
class Environment:
    account_id: str
    environment_id: str
    container_name: str
    volume_name: str
    state: str


def _uuid(value: str) -> str:
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError) as exc:
        raise RuntimeError("INVALID_ID") from exc


def _default_runner(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["docker", *args], capture_output=True, text=True,
                          encoding="utf-8", timeout=30, check=False)


class DockerEnvironmentBroker:
    def __init__(self, image: str, runner: Callable = _default_runner):
        if not re.fullmatch(r"[a-zA-Z0-9_./:@-]+", image):
            raise RuntimeError("INVALID_IMAGE")
        self.image = image
        self._run = runner
        self._lock = threading.RLock()

    @staticmethod
    def _names(environment_id: str) -> tuple[str, str]:
        suffix = _uuid(environment_id).replace("-", "")
        return "aetherdesk-e-" + suffix, "aetherdesk-v-" + suffix

    def _docker(self, *args: str, missing_ok: bool = False) -> str:
        result = self._run(args)
        if result.returncode:
            if missing_ok and ("No such container" in result.stderr or
                               "No such object" in result.stderr):
                return ""
            raise RuntimeError("RUNTIME_UNAVAILABLE", result.stderr.strip()[:400])
        return result.stdout.strip()

    def _inspect(self, name: str) -> tuple[str, str, str] | None:
        output = self._docker("container", "inspect", "--format",
                              "{{.State.Status}}|{{index .Config.Labels \"aetherdesk.account_id\"}}|{{index .Config.Labels \"aetherdesk.environment_id\"}}",
                              name, missing_ok=True)
        if not output:
            return None
        parts = output.split("|")
        if len(parts) != 3:
            raise RuntimeError("INVALID_RUNTIME_STATE")
        return parts[0], parts[1], parts[2]

    def ensure(self, account_id: str, environment_id: str) -> Environment:
        account_id, environment_id = _uuid(account_id), _uuid(environment_id)
        name, volume = self._names(environment_id)
        with self._lock:
            existing = self._inspect(name)
            if existing:
                state, label_account, label_environment = existing
                if (label_account, label_environment) != (account_id, environment_id):
                    raise RuntimeError("OWNERSHIP_MISMATCH")
                if state != "running":
                    self._docker("container", "start", name)
                return Environment(account_id, environment_id, name, volume, "running")
            self._docker("volume", "create", "--label", f"aetherdesk.account_id={account_id}",
                         "--label", f"aetherdesk.environment_id={environment_id}", volume)
            args = ("run", "--detach", "--name", name, "--network", "none", "--read-only",
                    "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
                    "--pids-limit", "128", "--memory", "512m", "--cpus", "1",
                    "--tmpfs", "/tmp:rw,noexec,nosuid,size=64m",
                    "--mount", f"type=volume,source={volume},target=/persist",
                    "--label", f"aetherdesk.account_id={account_id}",
                    "--label", f"aetherdesk.environment_id={environment_id}",
                    self.image)
            try:
                self._docker(*args)
            except RuntimeError:
                # Uma segunda instância do serviço pode ter vencido a corrida.
                existing = self._inspect(name)
                if not existing or existing[1:] != (account_id, environment_id):
                    raise
                if existing[0] != "running":
                    self._docker("container", "start", name)
            return Environment(account_id, environment_id, name, volume, "running")

    def state(self, account_id: str, environment_id: str) -> Environment:
        account_id, environment_id = _uuid(account_id), _uuid(environment_id)
        name, volume = self._names(environment_id)
        existing = self._inspect(name)
        if existing is None:
            return Environment(account_id, environment_id, name, volume, "absent")
        if existing[1:] != (account_id, environment_id):
            raise RuntimeError("OWNERSHIP_MISMATCH")
        return Environment(account_id, environment_id, name, volume, existing[0])

    def stop_session(self, account_id: str, environment_id: str) -> None:
        env = self.state(account_id, environment_id)
        if env.state == "running":
            self._docker("container", "stop", "--time", "5", env.container_name)

    def delete_account(self, account_id: str, environment_id: str) -> None:
        # A exclusão da conta remove o contêiner e preserva o volume.
        env = self.state(account_id, environment_id)
        if env.state == "running":
            self.stop_session(account_id, environment_id)
        if env.state != "absent":
            self._docker("container", "rm", env.container_name)

    def exec(self, account_id: str, environment_id: str,
             command: Sequence[str]) -> str:
        result = self.exec_status(account_id, environment_id, command)
        if result.returncode:
            raise RuntimeError("RUNTIME_UNAVAILABLE", result.stderr.strip()[:400])
        return result.stdout.strip()

    def exec_status(self, account_id: str, environment_id: str,
                    command: Sequence[str]):
        env = self.state(account_id, environment_id)
        if env.state != "running":
            raise RuntimeError("ENVIRONMENT_STOPPED")
        if not command or any("\x00" in part for part in command):
            raise RuntimeError("INVALID_COMMAND")
        return self._run(("exec", "--user", "10001:10001", env.container_name, *command))
