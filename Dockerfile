# Build stage: compiles the hash extensions and the ElectrumX checkout against
# the system RocksDB. Nothing from this stage is shipped except /install.
FROM python:3.12-trixie AS build

WORKDIR /app/plugins

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential cmake gcc g++ libffi-dev libssl-dev python3-dev curl \
    pkg-config libkrb5-dev librocksdb-dev libleveldb-dev libsnappy-dev liblz4-dev \
 && rm -rf /var/lib/apt/lists/*

# quark_hash sdist predates Python 3.12's mandatory PY_SSIZE_T_CLEAN
# ('#' C-API formats). REMOVE THIS ARG once the base image is Python >= 3.13.
ARG HASH_CFLAGS=-DPY_SSIZE_T_CLEAN

COPY requirements.txt .
RUN CFLAGS=${HASH_CFLAGS} pip install --no-cache-dir --prefix=/install -r requirements.txt

# Runtime stage: no compiler, no headers, no build dependencies.
FROM python:3.12-slim-trixie

# rocksdb-ng links the system RocksDB; plyvel and scrypt ship their own
# LevelDB and libcrypto inside the wheels. gosu drops privileges in the
# entrypoint, everything else is already in the python base.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu librocksdb9.10 libsnappy1v5 libgflags2.2 libxxhash0 \
 && rm -rf /var/lib/apt/lists/*

COPY --from=build /install/ /usr/local/

RUN useradd --create-home --uid 1000 utxo

WORKDIR /app/plugins
COPY --chown=utxo:utxo . /app/plugins
RUN chmod 755 /app/plugins/entrypoint.sh

# Build-time smoke: fails the image build if any hash extension regressed or a
# runtime shared library is missing from the slim base. kawpow exposes
# light_verify() only, so it is import-checked without a hash call.
RUN python3 -c "import quark_hash, dash_hash, kawpow, x16r_hash, x16rv2_hash, scrypt; \
    assert quark_hash.getPoWHash(b'') and \
           dash_hash.getPoWHash(b'') and x16r_hash.getPoWHash(b'') and \
           x16rv2_hash.getPoWHash(b'') and \
           scrypt.hash(b'verge-smoke', b'verge-smoke', 1024, 1, 1, 32)"

EXPOSE 8000 9000

ENTRYPOINT ["/app/plugins/entrypoint.sh"]
CMD ["python3", "/app/plugins/main.py"]
