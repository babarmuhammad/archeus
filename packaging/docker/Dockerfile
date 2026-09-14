# A real image, not a placeholder: archeus is pure standard library, so the
# whole thing is a slim Python plus one pip install.
#
# It runs the TUI, which needs a terminal — `docker run -it`. And it needs the
# host's Claude Code state to be useful at all, because that is the data it
# reads: mount `~/.claude` and whatever project you are asking about. Nothing
# here is a daemon.
#
#   docker build -t babarmuhammad/archeus packaging/docker
#   docker run -it --rm \
#       -v "$HOME/.claude:/root/.claude" \
#       -v "$PWD:/work" -w /work \
#       babarmuhammad/archeus
#
# The GUI is deliberately not exposed: it binds loopback with a per-run token,
# and publishing that port would put the whole API on the container's network
# interface, which is exactly what the Host allowlist exists to prevent.
FROM python:3.13-slim

# git, because archeus reads branch and worktree state for the project board
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

ARG ARCHEUS_VERSION=2.3.0
RUN pip install --no-cache-dir "archeus==${ARCHEUS_VERSION}"

LABEL org.opencontainers.image.title="archeus" \
      org.opencontainers.image.description="The memory and workspace layer for AI coding agents." \
      org.opencontainers.image.source="https://github.com/babarmuhammad/archeus" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${ARCHEUS_VERSION}"

WORKDIR /work
ENTRYPOINT ["archeus"]
