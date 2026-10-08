import electrumx.lib.tx as lib_tx
import quark_hash
from electrumx.lib import coins as upstream
from electrumx.lib import util
from electrumx.lib.coins import AuxPowMixin, Block
from electrumx.lib.coins import Coin as CoinBase

from server.session import AuxPoWElectrumX, ElectrumX


class Coin(CoinBase):
    SESSIONCLS = ElectrumX


class AuxPowHelper(AuxPowMixin):
    SESSIONCLS = AuxPoWElectrumX


class BlocknetMixin:
    NET = "mainnet"
    DESERIALIZER = lib_tx.DeserializerSegWit
    # C++ truth: https://github.com/blocknetdx/blocknet/blob/v4.4.0/src/primitives/block.h#L45-L58
    # CBlockHeader appends hashStake + nStakeIndex + nStakeAmount + hashStakeBlock:
    # transactions start at 156, not 80. Stored/announced headers stay the leading 80.
    FULL_HEADER_SIZE = 156
    # C++ truth: https://github.com/blocknetdx/blocknet/blob/v4.4.0/src/chainparams.cpp#L149-L150
    P2PKH_VERBYTE = bytes.fromhex("1A")
    P2SH_VERBYTES = bytes.fromhex("1C")
    GENESIS_HASH = "00000eb7919102da5a07dc90905651664e6ebf0811c28f06573b9a0fd84ab7b8"
    TX_COUNT = 10224729
    TX_COUNT_HEIGHT = 4799343
    TX_PER_BLOCK = 2

    @classmethod
    def block(cls, raw_block, height):
        header = cls.block_header(raw_block, height)
        txs = cls.DESERIALIZER(raw_block, start=cls.FULL_HEADER_SIZE).read_tx_block()
        return Block(raw_block, header, txs)


class Blocknet(BlocknetMixin, Coin):
    NAME = "Blocknet"
    SHORTNAME = "BLOCK"
    SHA256D_MIN_VERSION = 3

    @classmethod
    def header_hash(cls, header):
        (version,) = util.unpack_le_uint32_from(header)

        if len(header) != cls.BASIC_HEADER_SIZE and version >= cls.SHA256D_MIN_VERSION:
            return super().header_hash(header[: cls.BASIC_HEADER_SIZE])

        return quark_hash.getPoWHash(header[: cls.BASIC_HEADER_SIZE])


class BlocknetTestnetMixin(BlocknetMixin):
    NET = "testnet"
    DESERIALIZER = lib_tx.DeserializerSegWit
    # C++ truth: https://github.com/blocknetdx/blocknet/blob/v4.4.0/src/chainparams.cpp#L313-L314
    P2PKH_VERBYTE = bytes.fromhex("8B")
    P2SH_VERBYTES = bytes.fromhex("13")
    GENESIS_HASH = "0fd62ae4f74c7ee0c11ef60fc5a2e69a5c02eaee2e77b21c3db70934b5a5c8b9"
    TX_COUNT = 204387
    TX_COUNT_HEIGHT = 101910
    TX_PER_BLOCK = 2


class BlocknetTestnet(BlocknetTestnetMixin, Coin):
    NAME = "BlocknetTestnet"
    SHORTNAME = "TBLOCK"
    SHA256D_MIN_VERSION = 4

    @classmethod
    def header_hash(cls, header):
        (version,) = util.unpack_le_uint32_from(header)
        if version >= cls.SHA256D_MIN_VERSION:
            return super().header_hash(header)

        return quark_hash.getPoWHash(header)


class Syscoin(AuxPowHelper, Coin, upstream.Syscoin):
    pass


class BitcoinSegwit(Coin, upstream.BitcoinMainnet):
    pass


class Bitcore(Coin, upstream.Bitcore):
    pass


class Litecoin(Coin, upstream.Litecoin):
    pass


class DigiByte(Coin, upstream.DigiByte):
    # C++ truth: https://github.com/DigiByte-Core/digibyte/blob/v9.26.5/src/kernel/chainparams.cpp#L238
    P2SH_VERBYTES = bytes.fromhex("3f")


class Dogecoin(AuxPowHelper, Coin, upstream.Dogecoin):
    pass


class Dash(Coin, upstream.Dash):
    pass


class Ravencoin(Coin, upstream.Ravencoin):
    pass


class Pivx(Coin, upstream.Pivx):
    # C++ truth: https://github.com/PIVX-Project/PIVX/blob/v5.6.1/src/chainparams.cpp#L330
    P2SH_VERBYTES = bytes.fromhex("0d")


class BitcoinCash(Coin, upstream.BitcoinCash):
    pass


class Unobtanium(AuxPowHelper, Coin, upstream.Unobtanium):
    pass


class Pkoin(Coin):
    NAME = "Pocketcoin"
    SHORTNAME = "PKOIN"
    NET = "mainnet"
    # C++ truth: https://github.com/pocketnetteam/pocketnet.core/blob/0.22.21/src/chainparams.cpp#L170-L171
    P2PKH_VERBYTE = bytes.fromhex("37")
    P2SH_VERBYTES = bytes.fromhex("50")
    GENESIS_HASH = "00000fd0f6633d395541056e8adc32961e15f8133674b2e3937c4d210ced6f3f"
    TX_COUNT = 1
    TX_COUNT_HEIGHT = 1
    TX_PER_BLOCK = 1
    DESERIALIZER = lib_tx.DeserializerTxTimeSegWit


class Verge(Coin, upstream.Verge):
    # C++ truth: https://github.com/vergecurrency/verge/blob/v26.8/src/chainparams.cpp#L254-L255
    # C++ truth: https://github.com/vergecurrency/verge/blob/v26.8/src/amount.h#L18
    VALUE_PER_COIN = 1000000
    P2PKH_VERBYTE = bytes.fromhex("1e")
    P2SH_VERBYTES = bytes.fromhex("21")
