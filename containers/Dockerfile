FROM ubuntu:24.04

# Overriding LILYPOND_VERSION requires the matching LILYPOND_SHA256.
ARG LILYPOND_VERSION=2.24.4
ARG LILYPOND_SHA256=53bc1df875ee56dabe56ae1f0b4550237e0c9acc837b60f0ef8c42fc35a68641

RUN set -eux; \
    arch="$(dpkg --print-architecture)"; \
    if [ "$arch" != "amd64" ]; then \
      echo "error: LilyPond ${LILYPOND_VERSION} download is amd64-only; image architecture is $arch" >&2; \
      exit 1; \
    fi; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl fontconfig; \
    curl --fail --location --retry 3 \
      --output /tmp/lilypond.tar.gz \
      "https://gitlab.com/lilypond/lilypond/-/releases/v${LILYPOND_VERSION}/downloads/lilypond-${LILYPOND_VERSION}-linux-x86_64.tar.gz"; \
    echo "${LILYPOND_SHA256}  /tmp/lilypond.tar.gz" | sha256sum --check --strict -; \
    tar -xzf /tmp/lilypond.tar.gz -C /opt; \
    ln -s "/opt/lilypond-${LILYPOND_VERSION}/bin/lilypond" /usr/local/bin/lilypond; \
    rm -rf /var/lib/apt/lists/* /tmp/lilypond.tar.gz

WORKDIR /work
