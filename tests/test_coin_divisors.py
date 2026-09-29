import unittest
from types import SimpleNamespace

from main import coin_map
from server.session import ElectrumX
from server.utxoplugin_coins import Verge


class TestCoinDivisorSource(unittest.TestCase):
    """Each served coin resolves to a positive base-units divisor.

    The default (BTC standard) is inherited from upstream ElectrumX;
    only deviating coins set their own VALUE_PER_COIN. This file pins
    no roster and no default value, so coin additions need no test
    edits -- only a new deviation earns a named pin like Verge's.
    """

    def test_every_mapped_class_resolves_positive_divisor(self):
        for ticker, cls in coin_map.items():
            with self.subTest(ticker=ticker):
                factor = cls.VALUE_PER_COIN
                self.assertIsInstance(factor, int)
                self.assertGreater(factor, 0)

    def test_verge_divisor_is_1e6(self):
        # BCF verge conf COIN=1000000. Inherited 1e8 misprices XVG 100x.
        self.assertEqual(1000000, Verge.VALUE_PER_COIN)

    def test_server_features_exposes_class_divisor(self):
        env = SimpleNamespace(report_services=[], coin=Verge)
        features = ElectrumX.server_features(env)
        self.assertEqual(Verge.VALUE_PER_COIN,
                         features['value_per_coin'])


if __name__ == '__main__':
    unittest.main()
