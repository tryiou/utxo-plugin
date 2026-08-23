FROM python:3.12-trixie

WORKDIR /app/plugins

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake gcc g++ libffi-dev libssl-dev python3-dev curl \
    pkg-config libkrb5-dev librocksdb-dev libleveldb-dev libsnappy-dev liblz4-dev gosu \
 && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --uid 1000 utxo

# quark_hash/x11_hash sdists predate Python 3.12's mandatory PY_SSIZE_T_CLEAN
# ('#' C-API formats). REMOVE THIS ARG once the base image is Python >= 3.13.
ARG HASH_CFLAGS=-DPY_SSIZE_T_CLEAN

COPY requirements.txt .
RUN CFLAGS=${HASH_CFLAGS} sh -c '\
      pip install --no-cache-dir x11_hash && \
      pip install --no-cache-dir -r requirements.txt'

# Build-time smoke: fails the image build if any hash ext regresses (e.g. flag lost).
# kawpow exposes light_verify() only, so it is import-checked without a hash call.
RUN python3 -c "import quark_hash, x11_hash, dash_hash, kawpow, x16r_hash, x16rv2_hash; \
    assert quark_hash.getPoWHash(b'') and x11_hash.getPoWHash(b'') and \
           dash_hash.getPoWHash(b'') and x16r_hash.getPoWHash(b'') and \
           x16rv2_hash.getPoWHash(b'')"

COPY --chown=utxo:utxo . /app/plugins
RUN chmod 755 /app/plugins/entrypoint.sh

ENV EVENT_LOOP_POLICY="uvloop"

EXPOSE 8000 9000

ENTRYPOINT ["/app/plugins/entrypoint.sh"]
CMD ["python3", "/app/plugins/main.py"]
