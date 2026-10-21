# SonicSort's own debian:<suite>-slim, built from this fork (poslogica/debuerreotype,
# branch sonicsort/trixie). The rootfs comes from build_rootfs.py -- run it first:
#
#   python sonicsort/build_rootfs.py
#   docker build -t sonicsort-debian:local sonicsort
#
# This is the same shape as the official image (docker-debian-artifacts' Dockerfile:
# FROM scratch + ADD the debuerreotype rootfs), but from a rootfs we built ourselves
# at a snapshot.debian.org timestamp we chose (see rootfs/<suite>-slim.meta.json).
#
# ROOTFS_ARCH picks a foreign-arch rootfs (build_rootfs.py --arch <arch> writes
# rootfs/<suite>-slim-<arch>.tar.xz); pass it with the matching --platform.
FROM scratch
ARG SUITE=trixie
ARG ROOTFS_ARCH=
ADD rootfs/${SUITE}-slim${ROOTFS_ARCH:+-${ROOTFS_ARCH}}.tar.xz /
CMD ["bash"]
