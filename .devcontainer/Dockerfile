FROM nixos/nix:2.35.2 AS nix

ENV NIX_CONFIG="experimental-features = nix-command flakes"

WORKDIR /src

COPY flake.nix flake.lock ./

# Substitute from a BuildKit cache mount acting as a local binary cache, so a flake.lock change only downloads the paths that actually changed.
# Copy only the runtime closure of the environment, not the whole /nix (store db, flake inputs, build-time dependencies).
RUN --mount=type=cache,id=nix-binary-cache,target=/nix-cache --mount=type=cache,id=nix-user-cache,target=/root/.cache/nix \
    nix build path:/src --out-link /tmp/env \
    --option sandbox false --option build-users-group '' \
    --extra-substituters 'file:///nix-cache?trusted=1' \
    && nix copy --to 'file:///nix-cache?compression=zstd' /tmp/env \
    && mkdir -p /out/nix/store /out/opt \
    && cp -a $(nix path-info -r /tmp/env) /out/nix/store/ \
    && ln -s "$(readlink -f /tmp/env)" /out/opt/transplat-env

FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

ARG TZ=Asia/Seoul
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

ENV TZ=${TZ} \
    TZDIR=/opt/transplat-env/share/zoneinfo \
    LANG=C.UTF-8 \
    COLORTERM=truecolor \
    SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt \
    CLAUDE_CONFIG_DIR=/home/vscode/.config/claude \
    PATH=/opt/transplat-env/bin:${PATH}

# Host toolchain for the CUDA extensions and native libraries loaded by open3d/opencv; these must match the Ubuntu glibc, so they come from apt.
# ca-certificates backs SSL_CERT_FILE for the nix-built git/uv.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        ca-certificates \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=nix /out/ /

RUN ln -snf "${TZDIR}/${TZ}" /etc/localtime \
    && echo "${TZ}" >/etc/timezone \
    && echo /opt/transplat-env/bin/fish >>/etc/shells \
    && groupadd --gid "${USER_GID}" "${USERNAME}" \
    && useradd --uid "${USER_UID}" --gid "${USER_GID}" --create-home \
        --shell /opt/transplat-env/bin/fish "${USERNAME}" \
    && mkdir -p /home/${USERNAME}/.cache/uv /home/${USERNAME}/.config/claude/projects /home/${USERNAME}/.local/share/uv \
    && chown -R "${USERNAME}:${USERNAME}" /home/${USERNAME}

USER ${USERNAME}

WORKDIR /home/${USERNAME}
