FROM aetherdesk-runtime:w002
USER root
RUN apt-get update && apt-get install -y --no-install-recommends tmux \
    && rm -rf /var/lib/apt/lists/*
USER 10001:10001
CMD ["sleep", "infinity"]
