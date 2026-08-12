FROM ubuntu:24.04

ARG LILYPOND_VERSION=2.24.4

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl fontconfig \
    && curl --fail --location --retry 3 \
      --output /tmp/lilypond.tar.gz \
      "https://gitlab.com/lilypond/lilypond/-/releases/v${LILYPOND_VERSION}/downloads/lilypond-${LILYPOND_VERSION}-linux-x86_64.tar.gz" \
    && tar -xzf /tmp/lilypond.tar.gz -C /opt \
    && ln -s "/opt/lilypond-${LILYPOND_VERSION}/bin/lilypond" /usr/local/bin/lilypond \
    && rm -rf /var/lib/apt/lists/* /tmp/lilypond.tar.gz

WORKDIR /work
