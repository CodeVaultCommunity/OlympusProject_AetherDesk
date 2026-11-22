FROM debian:bookworm-slim
RUN groupadd --gid 10001 aether && useradd --uid 10001 --gid 10001 --home-dir /persist --shell /bin/bash --no-create-home aether \
    && mkdir /persist && chown 10001:10001 /persist \
    && ln -s /persist /dados && ln -s /persist/dados.txt /dados.txt
USER 10001:10001
WORKDIR /persist
CMD ["sleep", "infinity"]
