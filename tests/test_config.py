import unittest

from portle.config import reset_guild_ids


class ResetAllowlistTests(unittest.TestCase):
    def test_empty_disables_resets_and_lists_are_trimmed_and_deduplicated(self):
        self.assertEqual(reset_guild_ids(''),frozenset())
        self.assertEqual(reset_guild_ids('   '),frozenset())
        self.assertEqual(reset_guild_ids('22, 33,22'),frozenset({22,33}))

    def test_invalid_configuration_is_rejected_without_echoing_input(self):
        for value in ['*','all','0','-1','22;33','22,','22,,33','22,private-value','２２',str(2**64),'9'*10000]:
            with self.subTest(value=value[:30]):
                with self.assertRaises(ValueError) as caught:reset_guild_ids(value)
                self.assertIn('PORTLE_RESET_GUILD_IDS',str(caught.exception))
                self.assertNotIn('private-value',str(caught.exception))
