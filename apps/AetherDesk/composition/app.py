"""Integração de identidade e runtime no portão W002."""

from __future__ import annotations

from apps.AetherDesk.identity import ActorContext, IdentityService
from apps.AetherDesk.runtime import DockerEnvironmentBroker


class AppComposition:
    def __init__(self, identity: IdentityService, runtime: DockerEnvironmentBroker, terminal=None):
        self.identity = identity
        self.runtime = runtime
        self.terminal = terminal

    def ensure_personal_environment(self, actor: ActorContext):
        self.identity.assert_active(actor)
        account = self.identity.account(actor, actor.account_id)
        return self.runtime.ensure(account["id"], account["environment_id"])

    def stop_account_session(self, administrator: ActorContext, account_id: str):
        self.identity.require(administrator, "sessions.stop")
        account = self.identity.account(administrator, account_id)
        self.identity.revoke_all_sessions(administrator, account_id)
        self.runtime.stop_session(account_id, account["environment_id"])
        if self.terminal:
            self.terminal.close_all_for_account(account_id)

    def process_account_events(self, guard=None):
        for event in self.identity.pending_account_events():
            if guard is not None and not guard():
                return
            if event["event"] == "account.created":
                self.runtime.ensure(event["account_id"], event["environment_id"])
            elif event["event"] == "account.deleted":
                self.runtime.delete_account(event["account_id"], event["environment_id"])
                if self.terminal:
                    self.terminal.close_all_for_account(event["account_id"])
            elif event["event"] == "account.disabled":
                self.runtime.stop_session(event["account_id"], event["environment_id"])
                if self.terminal:
                    self.terminal.close_all_for_account(event["account_id"])
            if guard is None or guard():
                self.identity.mark_account_event_consumed(event["id"])
