import unittest

from .acronym_extractor import find_long_form, find_short_form, find_acronyms_in_text


class TestAcronym(unittest.TestCase):
    def test_simple(self):
        txt = 'This is a Simple Acronym Test SAT'
        res = find_acronyms_in_text(txt)
        self.assertTrue(res['matches'], {'SAT': 'Simple Acronym Test'})

    def test_multiple_occurrence(self):
        txt = 'This is SAT with a Simple Acronym Test SAT'
        res = find_acronyms_in_text(txt)
        self.assertTrue(res['matches'], {'SAT': 'Simple Acronym Test'})

    def test_no_long_form(self):
        txt = 'This is BLA a Simple Acronym Test SAT'
        res = find_acronyms_in_text(txt)
        self.assertTrue(res, {'SAT': 'Simple Acronym Test'})
        self.assertTrue(res['short_forms'], ['BLA', 'SAT'])


class TestAcronymShortForm(unittest.TestCase):
    def test_simple(self):
        text = 'This is ACRO nym'
        short = find_short_form(text)
        self.assertTrue(short[0], 'ACRO')

    def test_parenthesis(self):
        text = 'This is (ACRO) nym'
        short = find_short_form(text)
        self.assertTrue(short[0], 'ACRO')


class TestAcronymLongForm(unittest.TestCase):
    def test_simple(self):
        long = 'this is a Really Great Acronym'.split(' ')
        short = 'RGA'
        self.assertTrue(find_long_form(short, long), long[-3:])

    def test_no_match(self):
        long = 'this is a Really Bad Acronym'.split(' ')
        short = 'RGA'
        self.assertIsNone(find_long_form(short, long))

    def test_not_capitalized(self):
        long = 'this is a Really Great acronym'.split(' ')
        short = 'RGA'
        self.assertIsNone(find_long_form(short, long))

    def test_stopwords_within(self):
        long = 'this is a Really of Good Acronym'.split(' ')
        short = 'RGA'
        self.assertTrue(find_long_form(short, long), long[-3:])

    def test_single_letter(self):
        long = ['Alamos', 'National', 'Laboratory', 'Los', 'Alamos', 'NM', '87545', 'United', 'States', 'c', 'Colorado', 'School', 'of', 'Mines', 'Golden']
        short = 'CO'
        self.assertTrue(find_long_form(short, long), ['Colorado'])

    def test_stopwords_before(self):
        long = 'this is The Really Good Acronym'.split(' ')
        short = 'RGA'
        self.assertTrue(find_long_form(short, long), long[-3:])

    def test_two_letter_per_word(self):
        long = 'this is a Really Great Acronym'.split(' ')
        short = 'GRAC'
        self.assertTrue(find_long_form(short, long), long[-2:])


if __name__ == '__main__':
    unittest.main()
