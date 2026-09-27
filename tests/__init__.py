"""utxo-plugin unit tests.

Run inside the published image with the repo mounted read-only
(no host venv carries ``aiorpcx``/``electrumx``)::

    docker run --rm --entrypoint python3 \
        -v "$PWD:/repo:ro" -w /repo blocknetdx/utxo-plugin:local \
        -m unittest discover -s tests -v
"""
