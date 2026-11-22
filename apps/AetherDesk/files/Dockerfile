FROM aetherdesk-terminal:w003
USER root
RUN apt-get update && apt-get install -y --no-install-recommends python3 \
    && rm -rf /var/lib/apt/lists/*
COPY apps/AetherDesk/files/service.py /opt/aetherdesk/file_service.py
COPY apps/AetherDesk/files/agent.py /opt/aetherdesk/file_agent.py
USER 10001:10001
CMD ["sleep", "infinity"]
