import struct

import electrumx.lib.util as util
import electrumx.server.daemon as daemon
from electrumx.lib.coins import (
    AuxPowMixin, ScryptMixin, EquihashMixin, KomodoMixin, CoinError,
    Coin,
    # Import ElectrumX coin classes for reuse
    Bitcoin as ElectrumXBitcoin, Litecoin as ElectrumXLitecoin,
    DigiByte as ElectrumXDigiByte, Dogecoin as ElectrumXDogecoin,
    Dash as ElectrumXDash, Bitbay as ElectrumXBitbay,
    BitcoinCash as ElectrumXBitcoinCash, Unobtanium as ElectrumXUnobtanium,
    Syscoin as ElectrumXSyscoin, Ravencoin as ElectrumXRavencoin,
    Pivx as ElectrumXPivx, Trezarcoin as ElectrumXTrezarcoin,
    Polis as ElectrumXPolis, Bitcore as ElectrumXBitcore
)
from electrumx.lib.hash import double_sha256, hash_to_hex_str
from electrumx.lib.tx import (
    Deserializer, DeserializerSegWit, DeserializerLitecoin,
    DeserializerAuxPow, DeserializerAuxPowSegWit, DeserializerTxTime,
    DeserializerTxTimeSegWit, DeserializerTrezarcoin, DeserializerReddcoin,
    DeserializerEmercoin, DeserializerBitcoinAtom, DeserializerGroestlcoin,
    DeserializerPIVX, DeserializerSmartCash, DeserializerElectra,
    DeserializerECCoin, DeserializerZcoin, DeserializerXaya,
    DeserializerTokenPay, TxInputTokenPay, TxInputTokenPayStealth,
    TxInputDcr, TxOutputDcr, TxDcr, DeserializerDecred,
    TxBitcoinDiamond, TxBitcoinDiamondSegWit, DeserializerBitcoinDiamond,
    DeserializerBitcoinDiamondSegWit
)

from server.custom_session import CustomElectrumX


class Syscoin(ElectrumXSyscoin):
    """Syscoin - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Bitcoin(ElectrumXBitcoin):
    """Bitcoin - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class BitcoinSegwit(ElectrumXBitcoin):
    """Bitcoin SegWit - inherits from ElectrumX Bitcoin with custom session."""
    SESSIONCLS = CustomElectrumX
    

class Bitcore(ElectrumXBitcore):
    """Bitcore - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Litecoin(ElectrumXLitecoin):
    """Litecoin - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class DigiByte(ElectrumXDigiByte):
    """DigiByte - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Dogecoin(ElectrumXDogecoin):
    """Dogecoin - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Dash(ElectrumXDash):
    """Dash - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Polis(ElectrumXPolis):
    """Polis - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Bitbay(ElectrumXBitbay):
    """Bitbay - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Ravencoin(ElectrumXRavencoin):
    """Ravencoin - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Pivx(ElectrumXPivx):
    """PIVX - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Trezarcoin(ElectrumXTrezarcoin):
    """Trezarcoin - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class BitcoinCash(ElectrumXBitcoinCash):
    """Bitcoin Cash - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX


class Unobtanium(ElectrumXUnobtanium):
    """Unobtanium - inherits from ElectrumX with custom session/daemon."""
    SESSIONCLS = CustomElectrumX

class BlocknetTestnet():
    NET = "testnet"
    XPUB_VERBYTES = bytes.fromhex("3A8061A0")
    XPRV_VERBYTES = bytes.fromhex("3A805837")
    P2PKH_VERBYTE = bytes.fromhex("8B")
    P2SH_VERBYTES = [bytes.fromhex("13")]
    WIF_BYTE = bytes.fromhex("EF")
    GENESIS_HASH = ('0fd62ae4f74c7ee0c11ef60fc5a2e69a'
                    '5c02eaee2e77b21c3db70934b5a5c8b9')
    RPC_PORT = 41419
    TX_COUNT = 204387
    TX_COUNT_HEIGHT = 101910
    TX_PER_BLOCK = 2
    NAME = "BlocknetTestnet"
    SHORTNAME = "TBLOCK"
    SESSIONCLS = CustomElectrumX

    @classmethod
    def header_hash(cls, header):
        version, = util.unpack_le_uint32_from(header)
        if version >= 4:
            return super().header_hash(header)
        else:
            import quark_hash
            return quark_hash.getPoWHash(header)


class Blocknet(Coin):  # NOT IN ELECTRUMX
    NET = "mainnet"
    DAEMON = daemon.LegacyRPCDaemon
    DESERIALIZER = DeserializerSegWit
    SESSIONCLS = CustomElectrumX
    XPUB_VERBYTES = bytes.fromhex("0488B21E")
    XPRV_VERBYTES = bytes.fromhex("0488ADE4")
    P2PKH_VERBYTE = bytes.fromhex("1A")
    P2SH_VERBYTES = [bytes.fromhex("1C")]
    WIF_BYTE = bytes.fromhex("9A")
    GENESIS_HASH = ('00000eb7919102da5a07dc90905651664e6ebf0811c28f06573b9a0fd84ab7b8')
    RPC_PORT = 41414
    BASIC_HEADER_SIZE = 80
    TX_COUNT = 204387
    TX_COUNT_HEIGHT = 101910
    TX_PER_BLOCK = 2
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


class Phore(Coin):  # NOT IN ELECTRUMX
    NAME = "Phore"
    SHORTNAME = "PHR"
    NET = "mainnet"

    SESSIONCLS = CustomElectrumX
    DESERIALIZER = Deserializer
    XPUB_VERBYTES = bytes.fromhex("022D2533")
    XPRV_VERBYTES = bytes.fromhex("0221312B")
    GENESIS_HASH = ('2b1a0f66712aad59ad283662d5b91941'
                    '5a25921ce89511d73019107e380485bf')
    P2PKH_VERBYTE = bytes.fromhex("37")
    P2SH_VERBYTES = [bytes.fromhex("0d")]
    WIF_BYTE = bytes.fromhex("d4")
    BASIC_HEADER_SIZE = 80
    HDR_V4_SIZE = 112
    HDR_V4_HEIGHT = 89993
    HDR_V4_START_OFFSET = HDR_V4_HEIGHT * BASIC_HEADER_SIZE
    TX_COUNT_HEIGHT = 280600
    TX_COUNT = 635415
    TX_PER_BLOCK = 4
    RPC_PORT = 11771
    PEERS = []

    @classmethod
    def static_header_offset(cls, height):
        assert cls.STATIC_BLOCK_HEADERS
        if height >= cls.HDR_V4_HEIGHT:
            relative_v4_offset = (height - cls.HDR_V4_HEIGHT) * cls.HDR_V4_SIZE
            return cls.HDR_V4_START_OFFSET + relative_v4_offset
        else:
            return height * cls.BASIC_HEADER_SIZE

    @classmethod
    def header_hash(cls, header):
        version, = struct.unpack('<I', header[:4])
        if version >= 4:
            return super().header_hash(header)
        else:
            import quark_hash
            return quark_hash.getPoWHash(header)


class Alqo(Coin):  # NOT IN ELECTRUMX
    NAME = "Alqo"
    SHORTNAME = "XLQ"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("022D2533")
    XPRV_VERBYTES = bytes.fromhex("0221312B")
    GENESIS_HASH = ('000040f1123764b16ac29f9c6c994e5b'
                    'eeacaf21f751062f5ab2c651351e0db1')
    P2PKH_VERBYTE = bytes.fromhex("53")
    P2SH_VERBYTES = [bytes.fromhex("5A")]
    WIF_BYTE = bytes.fromhex("D3")
    TX_COUNT_HEIGHT = 280600
    TX_COUNT = 635415
    TX_PER_BLOCK = 4
    RPC_PORT = 11771
    PEERS = []
    SESSIONCLS = CustomElectrumX
    DESERIALIZER = Deserializer
    BASIC_HEADER_SIZE = 80
    # STATIC_BLOCK_HEADERS = True
    # ZEROCOIN_HEADER = 80
    # ZEROCOIN_START_HEIGHT = 33554432
    ZEROCOIN_BLOCK_VERSION = 4

    # ZEROCOIN_START_OFFSET = ZEROCOIN_START_HEIGHT * (BASIC_HEADER_SIZE - ZEROCOIN_HEADER)

    @classmethod
    def header_hash(cls, header):
        '''Given a header return the hash.'''
        version, = struct.unpack('<I', header[:4])

        if version == 1 or version >= cls.ZEROCOIN_BLOCK_VERSION:
            return super().header_hash(header[:cls.BASIC_HEADER_SIZE])
        else:
            import quark_hash
            return quark_hash.getPoWHash(header[:cls.BASIC_HEADER_SIZE])

    @classmethod
    def genesis_block(cls, block):
        '''Check the Genesis block is the right one for this coin.
        Return the block less its unspendable coinbase.
        '''
        header = cls.block_header(block, 0)
        header_hex_hash = hash_to_hex_str(super().header_hash(header[:cls.BASIC_HEADER_SIZE]))
        if header_hex_hash != cls.GENESIS_HASH:
            raise CoinError('genesis block has hash {} expected {}'
                            .format(header_hex_hash, cls.GENESIS_HASH))
        return header + bytes(1)


class Stakenet(Coin):  # NOT IN ELECTRUMX
    NAME = "Stakenet"
    SHORTNAME = "XSN"
    NET = "mainnet"
    XPUB_VERBYTES = bytes.fromhex("02fe52cc")
    XPRV_VERBYTES = bytes.fromhex("02fe52f8")
    GENESIS_HASH = ('00000c822abdbb23e28f79a49d29b414'
                    '29737c6c7e15df40d1b1f1b35907ae34')
    P2PKH_VERBYTE = bytes.fromhex("4c")
    P2SH_VERBYTES = [bytes.fromhex("10")]
    WIF_BYTE = bytes.fromhex("cc")
    TX_COUNT_HEIGHT = 569399
    TX_COUNT = 2157510
    TX_PER_BLOCK = 4
    RPC_PORT = 62583
    PEERS = []
    SESSIONCLS = CustomElectrumX
    DAEMON = daemon.Daemon
    DESERIALIZER = Deserializer

    @classmethod
    def header_hash(cls, header):
        '''Given a header return the hash.'''
        import x11_hash
        return x11_hash.getPoWHash(header)


class Pkoin(Coin):  # NOT IN ELECTRUMX
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
    SESSIONCLS = CustomElectrumX
    DAEMON = daemon.Daemon
    DESERIALIZER = DeserializerTxTimeSegWit
