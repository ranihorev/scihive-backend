import unittest

from .acronym_extractor import find_long_form


class TestAcronymExtractor(unittest.TestCase):
    def test_simple(self):
        long = 'this is a really great acronym'.split(' ')
        short = 'RGA'
        self.assertTrue(find_long_form(short, long), long[-3:])

    def test_no_match(self):
        long = 'this is a really bad acronym'.split(' ')
        short = 'RGA'
        self.assertIsNone(find_long_form(short, long))

    def test_stopwords(self):
        long = 'this is a really me good acronym'.split(' ')
        short = 'RGA'
        self.assertTrue(find_long_form(short, long), long[-3:])

    def test_single_letter(self):
        long = ['Alamos', 'National', 'Laboratory', 'Los', 'Alamos', 'NM', '87545', 'United', 'States', 'c', 'Colorado', 'School', 'of', 'Mines', 'Golden']
        short = 'CO'
        self.assertTrue(find_long_form(short, long), ['Colorado'])


if __name__ == '__main__':
    unittest.main()
