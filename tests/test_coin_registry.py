import unittest

from main import coin_map
from server.utxoplugin_coins import Coin


class TestCoinRegistryWellFormed(unittest.TestCase):
    """Every served coin entry is a well-formed Coin subclass.

    Structural invariants only: no roster or value is frozen here, so
    adding or delisting a coin never requires touching this file. Coin
    set agreement with BCF is enforced at deploy render time, not here.
    """

    def test_every_entry_is_a_coin_subclass(self):
        self.assertTrue(coin_map)
        for ticker, cls in coin_map.items():
            with self.subTest(ticker=ticker):
                self.assertTrue(issubclass(cls, Coin))

    def test_registry_key_matches_coin_shortname(self):
        for ticker, cls in coin_map.items():
            with self.subTest(ticker=ticker):
                self.assertEqual(ticker, cls.SHORTNAME)

    def test_every_entry_has_identity(self):
        for ticker, cls in coin_map.items():
            with self.subTest(ticker=ticker):
                self.assertIsInstance(cls.NAME, str)
                self.assertTrue(cls.NAME)
                self.assertIsNotNone(cls.NET)

    def test_every_entry_has_genesis_hash(self):
        # RPC_PORT is deliberately not asserted: serving uses the
        # DAEMON_RPC_PORT env value, and not every coin class sets one.
        for ticker, cls in coin_map.items():
            with self.subTest(ticker=ticker):
                self.assertRegex(cls.GENESIS_HASH, r"^[0-9a-f]{64}$")


if __name__ == "__main__":
    unittest.main()
