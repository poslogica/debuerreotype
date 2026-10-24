# SonicSort's own debian:<suite>-slim, built from this fork (poslogica/debuerreotype,
# branch basewarden/trixie). The rootfs comes from build_rootfs.py -- run it first:
#
#   python sonicsort/build_rootfs.py
#   docker build -t basewarden-debian:local sonicsort
#
# This is the same shape as the official image (docker-debian-artifacts' Dockerfile:
# FROM scratch + ADD the debuerreotype rootfs), but from a rootfs we built ourselves
# at a snapshot.debian.org timestamp we chose (see rootfs/<suite>-slim.meta.json).
#
# ROOTFS_ARCH picks a foreign-arch rootfs (build_rootfs.py --arch <arch> writes
# rootfs/<suite>-slim-<arch>.tar.xz); pass it with the matching --platform.
FROM scratch AS rootfs
ARG SUITE=trixie
ARG ROOTFS_ARCH=
ADD rootfs/${SUITE}-slim${ROOTFS_ARCH:+-${ROOTFS_ARCH}}.tar.xz /

# Patched zlib for CVE-2026-85091 (patches/zlib/CVE-2026-85091.patch), which
# Debian hasn't fixed for trixie yet. The source is Debian's own, for the
# version the rootfs carries: apt checks it against the archive's signed index,
# and it is pinned here by the .dsc's sha256, which pins the tarballs
# dpkg-source then checks. On top of it goes the upstream maintainer's fix.
# The build runs with no network: zlib's own tests, then
# patches/zlib/test_cve_2026_85091.c under AddressSanitizer, against the
# rootfs's zlib (it should overflow) and against ours (it must not).
#
# The version is <Debian's>+bw1. That sorts above trixie's -1+b1 and below a
# Debian security update (+deb13u1), so when Debian ships its fix, apt takes
# it over and the final stage stops installing ours. Drop this stage then;
# the stock test below says so once the rootfs's zlib stops overflowing.
FROM rootfs AS zlib
ARG ZLIB_VERSION=1:1.3.dfsg+really1.3.1-1
ARG ZLIB_DSC=zlib_1.3.dfsg+really1.3.1-1.dsc
ARG ZLIB_DSC_SHA256=ede2791e29c1d3b422f9208bdd7edf040c20445ea1e7453a72037576e64fa197
ENV DEBIAN_FRONTEND=noninteractive
RUN set -eux; \
    sed -i 's/^Types: deb$/Types: deb deb-src/' /etc/apt/sources.list.d/debian.sources; \
    apt-get update; \
    apt-get install -y --no-install-recommends build-essential dpkg-dev apt-utils zlib1g-dev; \
    apt-get build-dep -y "zlib=${ZLIB_VERSION}"; \
    mkdir /src; cd /src; \
    apt-get source --download-only "zlib=${ZLIB_VERSION}"; \
    echo "${ZLIB_DSC_SHA256}  ${ZLIB_DSC}" | sha256sum -c -; \
    dpkg-source -x "${ZLIB_DSC}" zlib
COPY patches/zlib/ /patches/
RUN --network=none set -eux; \
    cd /src/zlib; \
    cp /patches/CVE-2026-85091.patch debian/patches/; \
    echo CVE-2026-85091.patch >> debian/patches/series; \
    version="$(dpkg-parsechangelog -S Version)+bw1"; \
    { printf 'zlib (%s) trixie-security; urgency=high\n\n' "$version"; \
      printf '  * Backport upstream fix for CVE-2026-85091 (madler/zlib df84af25).\n\n'; \
      printf ' -- basewarden <basewarden@poslogica.invalid>  %s\n\n' "$(dpkg-parsechangelog -S Date)"; \
      cat debian/changelog; } > debian/changelog.new; \
    mv debian/changelog.new debian/changelog; \
    dpkg-buildpackage -B -uc -us -j"$(nproc)"; \
    gcc -g -fsanitize=address -o /tmp/test /patches/test_cve_2026_85091.c -lz; \
    if /tmp/test > /tmp/stock.log 2>&1; then \
      echo "NOTE: the rootfs's zlib no longer overflows -- Debian's fix has landed; drop the zlib stage"; \
    else \
      grep -q 'heap-buffer-overflow' /tmp/stock.log; \
      echo "rootfs zlib: CVE-2026-85091 reproduced, as expected"; \
    fi; \
    mkdir /debs; \
    cp /src/zlib1g_*.deb /src/zlib1g-dev_*.deb /debs/; \
    dpkg -i /debs/*.deb; \
    /tmp/test; \
    cd /debs; \
    dpkg-scanpackages --multiversion . > Packages; \
    apt-ftparchive release . > Release

FROM rootfs
# Install our zlib1g only while it is newer than the rootfs's. Keep zlib1g and
# zlib1g-dev as a local apt repository, so an image built FROM this one that
# installs zlib1g-dev (python's build does) gets the matching patched version,
# instead of failing on zlib1g-dev's exact-version dependency on zlib1g. The
# repository is a directory in this image, written by the stage above:
# [trusted=yes] only means apt doesn't look for a signature on it. Images that
# take zlib1g from here (redpanda's) COPY the directory, so it stays, empty,
# when ours isn't installed.
COPY --from=zlib /debs/ /var/lib/basewarden/apt/
RUN set -eu; \
    ours="$(dpkg-deb -f /var/lib/basewarden/apt/zlib1g_*.deb Version)"; \
    have="$(dpkg-query -W -f '${Version}' zlib1g)"; \
    if dpkg --compare-versions "$ours" gt "$have"; then \
      dpkg -i /var/lib/basewarden/apt/zlib1g_*.deb; \
      echo 'deb [trusted=yes] file:/var/lib/basewarden/apt ./' > /etc/apt/sources.list.d/basewarden.list; \
    else \
      echo "zlib1g $have is already at or past ours ($ours): not installing the patched build"; \
      rm -f /var/lib/basewarden/apt/*; \
    fi
CMD ["bash"]
