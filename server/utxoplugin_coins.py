import struct
import electrumx.lib.tx as lib_tx
import electrumx.lib.tx_dash as lib_tx_dash
#import lib.tx as lib_tx
#import lib.tx_dash as lib_tx_dash
#import lib.coins as BlockProc

import electrumx.lib.util as util
import electrumx.server.daemon as daemon
import electrumx.server.block_processor as block_proc

from hashlib import sha256
from electrumx.lib.script import OpCodes, _match_ops, ScriptPubKey
from electrumx.lib.coins import AuxPowMixin, Coin as CoinBase
from electrumx.lib.coins import Verge as UpstreamVerge
from electrumx.lib.hash import double_sha256, HASHX_LEN

from server.daemon import SyscoinDaemon
from server.session import (ElectrumX, BitcoinSegwitElectrumX, DashElectrumX,
                            SmartCashElectrumX, AuxPoWElectrumX, SyscoinElectrumX)
class Coin(CoinBase):
    DESERIALIZER = lib_tx.Deserializer
    DAEMON = daemon.Daemon
    BLOCK_PROCESSOR = block_proc.BlockProcessor
    SESSIONCLS = ElectrumX
    REORG_LIMIT = 2000


class AuxPowHelper(AuxPowMixin):
    SESSIONCLS = AuxPoWElectrumX
    DESERIALIZER = lib_tx.DeserializerAuxPow


class BlocknetMixin(object):
    NET = "mainnet"
    DAEMON = daemon.LegacyRPCDaemon
    DESERIALIZER = lib_tx.DeserializerSegWit
    XPUB_VERBYTES = bytes.fromhex("0488B21E")
    XPRV_VERBYTES = bytes.fromhex("0488ADE4")
    P2PKH_VERBYTE = bytes.fromhex("1A")
    P2SH_VERBYTES = [bytes.fromhex("1C")]
    WIF_BYTE = bytes.fromhex("9A")
    GENESIS_HASH = ('00000eb7919102da5a07dc90905651664e6ebf0811c28f06573b9a0fd84ab7b8')
    RPC_PORT = 41414
    #  HDR_V4_HEIGHT = 1
    #  HDR_V4_SIZE = 112
    BASIC_HEADER_SIZE = 80
    TX_COUNT = 204387
    TX_COUNT_HEIGHT = 101910
    TX_PER_BLOCK = 2
    #  HDR_V4_START_OFFSET = HDR_V4_HEIGHT * BASIC_HEADER_SIZE


class Blocknet(BlocknetMixin, Coin):
    NAME = "Blocknet"
    SHORTNAME = "BLOCK"

    @classmethod
    def header_hash(cls, header):
        version, = util.unpack_le_uint32_from(header)

        if len(header) != 80 and version >= 3:
            return super().header_hash(header[:cls.BASIC_HEADER_SIZE])
        else:
            import quark_hash
            return quark_hash.getPoWHash(header[:cls.BASIC_HEADER_SIZE])


class BlocknetTestnetMixin(object):
    NET = "testnet"
    XPUB_VERBYTES = bytes.fromhex("3A8061A0")
    XPRV_VERBYTES = bytes.fromhex("3A805837")
    P2PKH_VERBYTE = bytes.fromhex("8B")
    P2SH_VERBYTES = [bytes.fromhex("13")]
    WIF_BYTE = bytes.fromhex("EF")
    GENESIS_HASH = ('0fd62ae4f74c7ee0c11ef60fc5a2e69a'
                    '5c02eaee2e77b21c3db70934b5a5c8b9')
    RPC_PORT = 41419
    #  HDR_V4_HEIGHT = 1
    #  HDR_V4_SIZE = 112
    TX_COUNT = 204387
    TX_COUNT_HEIGHT = 101910
    TX_PER_BLOCK = 2
    #  HDR_V4_START_OFFSET = HDR_V4_HEIGHT * BASIC_HEADER_SIZE


class BlocknetTestnet(BlocknetTestnetMixin, Coin):
    NAME = "BlocknetTestnet"
    SHORTNAME = "TBLOCK"

    @classmethod
    def header_hash(cls, header):
        version, = util.unpack_le_uint32_from(header)
        if version >= 4:
            return super().header_hash(header)
        else:
            import quark_hash
            return quark_hash.getPoWHash(header)


class Syscoin(AuxPowHelper, Coin):
    NAME = "Syscoin"
    SHORTNAME = "SYS"
    NET = "mainnet"

    P2PKH_VERBYTE = bytes.fromhex("3f")
    P2SH_VERBYTES = (bytes.fromhex("05"),)
    WIF_BYTE = bytes.fromhex("80")

    GENESIS_HASH = '0000022642db0346b6e01c2a397471f4f12e65d4f4251ec96c1f85367a61a7ab'
    TX_COUNT = 17036
    TX_COUNT_HEIGHT = 16485
    TX_PER_BLOCK = 5
    RPC_PORT = 8368

    DEFAULT_COST_SOFT_LIMIT = 0
    DEFAULT_COST_HARD_LIMIT = 0
    DEFAULT_BANDWIDTH_UNIT_COST = 5000
    DEFAULT_INITIAL_CONCURRENT = 10

    # auxpow header params are not static
    STATIC_BLOCK_HEADERS = False
    BASIC_HEADER_SIZE = 80

    # AuxPoW headers are significantly larger, so the DEFAULT_MAX_SEND from
    # Bitcoin is insufficient.  In Syscoin mainnet, 5 MB wasn't enough to
    # sync, while 10 MB worked fine.
    DEFAULT_MAX_SEND = 10000000

    DAEMON = SyscoinDaemon
    SESSIONCLS = SyscoinElectrumX
    DESERIALIZER = lib_tx.DeserializerAuxPowSegWit


class BitcoinMixin(object):
    SHORTNAME = "BTC"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("0488b21e")
    XPRV_VERBYTES = bytes.fromhex("0488ade4")
    P2PKH_VERBYTE = bytes.fromhex("00")
    P2SH_VERBYTES = [bytes.fromhex("05")]
    WIF_BYTE = bytes.fromhex("80")
    GENESIS_HASH = ('000000000019d6689c085ae165831e93'
                    '4ff763ae46a2a6c172b3f1b60a8ce26f')
    RPC_PORT = 8332


class Bitcoin(BitcoinMixin, Coin):
    NAME = "Bitcoin"
    DESERIALIZER = lib_tx.Deserializer

    TX_COUNT = 217380620
    TX_COUNT_HEIGHT = 464000
    TX_PER_BLOCK = 1800


class BitcoinSegwit(BitcoinMixin, Coin):
    NAME = "BitcoinSegwit"
    DESERIALIZER = lib_tx.DeserializerSegWit
    SESSIONCLS = BitcoinSegwitElectrumX
    MEMPOOL_HISTOGRAM_REFRESH_SECS = 120
    TX_COUNT = 318337769
    TX_COUNT_HEIGHT = 524213
    TX_PER_BLOCK = 1400
    BLACKLIST_URL = 'https://electrum.org/blacklist.json'
    PEERS = [
        'btc.smsys.me s995',
        'E-X.not.fyi s t',
        'elec.luggs.co s443',
        'electrum.vom-stausee.de s t',
        'electrum.hsmiths.com s t',
        'helicarrier.bauerj.eu s t',
        'hsmiths4fyqlw5xw.onion s t',
        'luggscoqbymhvnkp.onion t80',
        'ozahtqwp25chjdjd.onion s t',
        'node.arihanc.com s t',
        'arihancckjge66iv.onion s t',
    ]

    @classmethod
    def warn_old_client_on_tx_broadcast(cls, client_ver):
        if client_ver < (3, 3, 3):
            return ('<br/><br/>'
                    'Your transaction was successfully broadcast.<br/><br/>'
                    'However, you are using a VULNERABLE version of Electrum.<br/>'
                    'Download the new version from the usual place:<br/>'
                    'https://electrum.org/'
                    '<br/><br/>')
        return False


class Bitcore(BitcoinMixin, Coin):
    NAME = "Bitcore"
    SHORTNAME = "BTX"
    P2PKH_VERBYTE = bytes.fromhex("03")
    P2SH_VERBYTES = [bytes.fromhex("7D")]
    WIF_BYTE = bytes.fromhex("80")
    DESERIALIZER = lib_tx.DeserializerSegWit
    GENESIS_HASH = ('604148281e5c4b7f2487e5d03cd60d8e'
                    '6f69411d613f6448034508cea52e9574')
    TX_COUNT = 126979
    TX_COUNT_HEIGHT = 126946
    TX_PER_BLOCK = 2
    RPC_PORT = 8556


class Litecoin(Coin):
    NAME = "Litecoin"
    SHORTNAME = "LTC"
    NET = "mainnet"

    # DAEMON = daemon.LegacyRPCDaemon

    XPUB_VERBYTES = bytes.fromhex("0488b21e")
    XPRV_VERBYTES = bytes.fromhex("0488ade4")
    P2PKH_VERBYTE = bytes.fromhex("30")
    P2SH_VERBYTES = (bytes.fromhex("32"), bytes.fromhex("05"))
    WIF_BYTE = bytes.fromhex("b0")
    GENESIS_HASH = ('12a765e31ffd4059bada1e25190f6e98'
                    'c99d9714d334efa41a195a7e7e04bfe2')
    DESERIALIZER = lib_tx.DeserializerLitecoin
    TX_COUNT = 8908766
    TX_COUNT_HEIGHT = 1105256
    TX_PER_BLOCK = 10
    RPC_PORT = 9332


class DigiByte(Coin):
    NAME = "DigiByte"
    SHORTNAME = "DGB"
    NET = "mainnet"
    P2PKH_VERBYTE = bytes.fromhex("1E")
    P2SH_VERBYTES = [bytes.fromhex("05")]
    WIF_BYTE = bytes.fromhex("80")
    GENESIS_HASH = ('7497ea1b465eb39f1c8f507bc877078f'
                    'e016d6fcb6dfad3a64c98dcc6e1e8496')
    DESERIALIZER = lib_tx.DeserializerSegWit
    TX_COUNT = 1046018
    TX_COUNT_HEIGHT = 1435000
    TX_PER_BLOCK = 1000
    RPC_PORT = 12022


class Dogecoin(AuxPowHelper, Coin):
    NAME = "Dogecoin"
    SHORTNAME = "DOGE"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("02facafd")
    XPRV_VERBYTES = bytes.fromhex("02fac398")
    P2PKH_VERBYTE = bytes.fromhex("1e")
    P2SH_VERBYTES = [bytes.fromhex("16")]
    WIF_BYTE = bytes.fromhex("9e")
    GENESIS_HASH = ('1a91e3dace36e2be3bf030a65679fe82'
                    '1aa1d6ef92e7c9902eb318182c355691')
    TX_COUNT = 27583427
    TX_COUNT_HEIGHT = 1604979
    TX_PER_BLOCK = 20
    PEERS = []
    DESERIALIZER = lib_tx.DeserializerAuxPowSegWit


# Source: https://github.com/dashpay/dash
class Dash(Coin):
    NAME = "Dash"
    SHORTNAME = "DASH"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("02fe52cc")
    XPRV_VERBYTES = bytes.fromhex("02fe52f8")
    GENESIS_HASH = ('00000ffd590b1485b3caadc19b22e637'
                    '9c733355108f107a430458cdf3407ab6')
    P2PKH_VERBYTE = bytes.fromhex("4c")
    P2SH_VERBYTES = (bytes.fromhex("10"),)
    WIF_BYTE = bytes.fromhex("cc")
    TX_COUNT_HEIGHT = 569399
    TX_COUNT = 2157510
    TX_PER_BLOCK = 4
    RPC_PORT = 9998
    PEERS = []
    SESSIONCLS = DashElectrumX
    DAEMON = daemon.DashDaemon
    DESERIALIZER = lib_tx_dash.DeserializerDash

    @classmethod
    def header_hash(cls, header):
        '''Given a header return the hash.'''
        import dash_hash
        return dash_hash.getPoWHash(header)


class Ravencoin(Coin):
    NAME = "Ravencoin"
    SHORTNAME = "RVN"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("0488B21E")
    XPRV_VERBYTES = bytes.fromhex("0488ADE4")
    P2PKH_VERBYTE = bytes.fromhex("3C")
    P2SH_VERBYTES = (bytes.fromhex("7A"),)
    GENESIS_HASH = ('0000006b444bc2f2ffe627be9d9e7e7a'
                    '0730000870ef6eb6da46c8eae389df90')
    DESERIALIZER = lib_tx.DeserializerSegWit
    X16RV2_ACTIVATION_TIME = 1569945600   # algo switch to x16rv2 at this timestamp
    KAWPOW_ACTIVATION_TIME = 1588788000  # kawpow algo activation time
    KAWPOW_ACTIVATION_HEIGHT = 1219736
    KAWPOW_HEADER_SIZE = 120
    TX_COUNT = 5626682
    TX_COUNT_HEIGHT = 887000
    TX_PER_BLOCK = 6
    RPC_PORT = 8766
    REORG_LIMIT = 100
    PEERS = [
    ]

    @classmethod
    def static_header_offset(cls, height):
        '''Given a header height return its offset in the headers file.'''
        if cls.KAWPOW_ACTIVATION_HEIGHT < 0 or height <= cls.KAWPOW_ACTIVATION_HEIGHT:
            result = height * cls.BASIC_HEADER_SIZE
        else:  # RVN block header size increased with kawpow fork
            baseoffset = cls.KAWPOW_ACTIVATION_HEIGHT * cls.BASIC_HEADER_SIZE
            result = baseoffset + ((height-cls.KAWPOW_ACTIVATION_HEIGHT) * cls.KAWPOW_HEADER_SIZE)
        return result

    @classmethod
    def header_hash(cls, header):
        '''Given a header return the hash.'''
        timestamp = util.unpack_le_uint32_from(header, 68)[0]
        assert cls.KAWPOW_ACTIVATION_TIME > 0

        def reverse_bytes(data):
            b = bytearray(data)
            b.reverse()
            return bytes(b)

        if timestamp >= cls.KAWPOW_ACTIVATION_TIME:
            import kawpow
            nNonce64 = util.unpack_le_uint64_from(header, 80)[0]  # uint64_t
            mix_hash = reverse_bytes(header[88:120])  # uint256

            header_hash = reverse_bytes(double_sha256(header[:80]))

            final_hash = reverse_bytes(kawpow.light_verify(header_hash, mix_hash, nNonce64))
            return final_hash

        elif timestamp >= cls.X16RV2_ACTIVATION_TIME:
            import x16rv2_hash
            return x16rv2_hash.getPoWHash(header)
        else:
            import x16r_hash
            return x16r_hash.getPoWHash(header)


class Pivx(Coin):
    NAME = "PIVX"
    SHORTNAME = "PIVX"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("022D2533")
    XPRV_VERBYTES = bytes.fromhex("0221312B")
    GENESIS_HASH = '0000041e482b9b9691d98eefb48473405c0b8ec31b76df3797c74a78680ef818'
    P2PKH_VERBYTE = bytes.fromhex("1e")
    P2SH_VERBYTES = (bytes.fromhex("0d"),)
    WIF_BYTE = bytes.fromhex("d4")
    DESERIALIZER = lib_tx.DeserializerPIVX
    TX_COUNT_HEIGHT = 569399
    TX_COUNT = 2157510
    TX_PER_BLOCK = 1
    STATIC_BLOCK_HEADERS = False
    RPC_PORT = 51470
    REORG_LIMIT = 100
    EXPANDED_HEADER = 112
    ZEROCOIN_START_HEIGHT = 863787
    ZEROCOIN_END_HEIGHT = 2153200
    ZEROCOIN_BLOCK_VERSION = 4
    SAPLING_START_HEIGHT = 2700500

    @classmethod
    def static_header_len(cls, height):
        '''Given a header height return its length.'''
        if (height >= cls.ZEROCOIN_START_HEIGHT and height < cls.ZEROCOIN_END_HEIGHT) \
                or (height >= cls.SAPLING_START_HEIGHT):
            return cls.EXPANDED_HEADER
        else:
            return cls.BASIC_HEADER_SIZE

    @classmethod
    def header_hash(cls, header):
        '''Given a header return the hash.'''
        version, = struct.unpack('<I', header[:4])
        if version >= cls.ZEROCOIN_BLOCK_VERSION:
            return super().header_hash(header)
        else:
            import quark_hash
            return quark_hash.getPoWHash(header)


class BitcoinCash(BitcoinMixin, Coin):
    NAME = "BitcoinCashABC"
    SHORTNAME = "BCH"
    TX_COUNT = 265479628
    TX_COUNT_HEIGHT = 556592
    TX_PER_BLOCK = 400
    PEERS = [
        'bch.imaginary.cash s t',
        'electroncash.dk s t',
        'wallet.satoshiscoffeehouse.com s t',
    ]
    BLOCK_PROCESSOR = block_proc.LTORBlockProcessor


class Unobtanium(AuxPowHelper, Coin):
    NAME = "Unobtanium"
    SHORTNAME = "UNO"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("0488B21E")
    XPRV_VERBYTES = bytes.fromhex("0488ADE4")
    P2PKH_VERBYTE = bytes.fromhex("82")
    P2SH_VERBYTES = (bytes.fromhex("1e"),)
    WIF_BYTE = bytes.fromhex("e0")
    GENESIS_HASH = ('000004c2fc5fffb810dccc197d603690'
                    '099a68305232e552d96ccbe8e2c52b75')
    TX_COUNT = 1
    TX_COUNT_HEIGHT = 1
    TX_PER_BLOCK = 1
    RPC_PORT = 65535
    REORG_LIMIT = 5000


class Pkoin(Coin):
    NAME = "Pocketcoin"
    SHORTNAME = "PKOIN"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("1E88B21E")
    XPRV_VERBYTES = bytes.fromhex("1E88ADE4")
    P2PKH_VERBYTE = bytes.fromhex("37")
    P2SH_VERBYTES = (bytes.fromhex("50"),)
    WIF_BYTE = bytes.fromhex("21")
    GENESIS_HASH = ('00000fd0f6633d395541056e8adc3296'
                    '1e15f8133674b2e3937c4d210ced6f3f')
    RPC_PORT = 37071
    TX_COUNT = 1
    TX_COUNT_HEIGHT = 1
    TX_PER_BLOCK = 1
    DESERIALIZER = lib_tx.DeserializerTxTimeSegWit


# Source: https://github.com/vergecurrency/verge (tag v26.8). Parameters
# inherited from the ElectrumX 1.20.0 upstream reference class (genesis hash,
# ports, tx-time deserializer) instead of duplicating them. MRO
# (UpstreamVerge first) keeps upstream DESERIALIZER while local Coin supplies
# SESSIONCLS/DAEMON/REORG_LIMIT. Explicitly overridden (NOT inherited):
# - NAME/SHORTNAME pin identity (also opts into the conformance sweep);
# - P2PKH_VERBYTE/P2SH_VERBYTES: upstream transcribes Verge's DECIMAL
#   chainparams (30/33) as hex (0x30/0x33); correct bytes from
#   src/chainparams.cpp (PUBKEY_ADDRESS=30, SCRIPT_ADDRESS=33) are
#   0x1e/0x21. Inheriting upstream here rejects every real wallet address;
# - WIF_BYTE: upstream defines none; Verge uses 0x9E (SECRET_KEY=158);
# - header_hash: stdlib hashlib.scrypt instead of upstream's PyPI `scrypt`
#   package, so no new dependency is required.
class Verge(UpstreamVerge, Coin):
    NAME = "Verge"
    SHORTNAME = "XVG"
    P2PKH_VERBYTE = bytes.fromhex("1e")
    P2SH_VERBYTES = [bytes.fromhex("21")]
    WIF_BYTE = bytes.fromhex("9e")

    @classmethod
    def header_hash(cls, header):
        from hashlib import scrypt
        return scrypt(header, salt=header, n=1024, r=1, p=1, dklen=32)