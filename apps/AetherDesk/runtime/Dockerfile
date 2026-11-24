FROM debian:trixie-slim@sha256:8aa5a7bf5a1955bddbe7d74fcdd0b91ab30e74362a8b73af672b0481b35b44a0
RUN groupadd --gid 10001 aether && useradd --uid 10001 --gid 10001 --home-dir /persist --shell /bin/bash --no-create-home aether \
    && mkdir /persist && chown 10001:10001 /persist \
    && ln -s /persist /dados && ln -s /persist/dados.txt /dados.txt
USER 10001:10001
WORKDIR /persist
CMD ["sleep", "infinity"]
