FROM nixos/nix:2.35.2 AS nix

COPY flake.nix flake.lock /src/

RUN --mount=type=cache,id=nix-binary-cache,target=/nix-cache \
    --mount=type=cache,id=nix-user-cache,target=/root/.cache/nix \
    nix \
    --extra-experimental-features 'nix-command flakes' \
    --option sandbox false \
    --option build-users-group '' \
    --extra-substituters 'file:///nix-cache?trusted=1' \
    profile add --profile /nix/var/nix/profiles/transplat path:/src \
    && nix \
    --extra-experimental-features 'nix-command' \
    copy --to 'file:///nix-cache?compression=zstd' /nix/var/nix/profiles/transplat \
    && nix-collect-garbage

FROM nvidia/cuda:11.8.0-devel-ubuntu22.04

ARG TZ=Asia/Seoul
ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=1000

ENV TZ=${TZ} \
    LANG=C.UTF-8 \
    COLORTERM=truecolor \
    PATH=/nix/var/nix/profiles/transplat/bin:${PATH}

# Host toolchain for the CUDA extensions and native libraries loaded by
# open3d/opencv; these must match the Ubuntu glibc, so they come from apt.
RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        build-essential \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=nix /nix /nix

RUN rm -rf /usr/share/zoneinfo \
    && ln -s /nix/var/nix/profiles/transplat/share/zoneinfo /usr/share/zoneinfo \
    && ln -snf "/usr/share/zoneinfo/${TZ}" /etc/localtime \
    && echo "${TZ}" >/etc/timezone \
    && echo /nix/var/nix/profiles/transplat/bin/fish >>/etc/shells \
    && groupadd --gid "${USER_GID}" "${USERNAME}" \
    && useradd --uid "${USER_UID}" --gid "${USER_GID}" --create-home \
        --shell /nix/var/nix/profiles/transplat/bin/fish "${USERNAME}"

USER ${USERNAME}
