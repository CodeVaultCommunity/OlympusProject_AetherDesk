FROM aetherdesk-terminal:w003
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 git \
    && rm -rf /var/lib/apt/lists/*
COPY apps/AetherDesk/files/service.py /opt/aetherdesk/file_service.py
COPY apps/AetherDesk/files/agent.py /opt/aetherdesk/file_agent.py
COPY apps/AetherDesk/workspace/files.py /opt/aetherdesk/workspace_files.py
COPY apps/AetherDesk/workspace/git.py /opt/aetherdesk/git_workspace.py
RUN touch /opt/aetherdesk/.aetherdesk-file-stream-v1 /opt/aetherdesk/.aetherdesk-workspace-v2
USER 10001:10001
CMD ["sleep", "infinity"]
