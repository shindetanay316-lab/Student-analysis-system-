import unittest

from result_data.parsers.dbatu_cr_parser import DBATUCrystalReportParser


class DBATUCrystalReportParserLayoutTests(unittest.TestCase):
    def setUp(self):
        self.parser = DBATUCrystalReportParser()

    def test_student_offsets_support_one_ese_row(self):
        offsets = self.parser._student_row_offsets(
            {
                "CREDIT": [157.88],
                "ESE TOTAL": [172.53],
                "CA INTERNAL": [187.18],
                "MID INTERNAL": [201.83],
                "INT TOTAL": [216.48],
                "TOTAL": [231.13],
            }
        )

        expected = {
            "ESE_0": 10.54,
            "CA": 29.14,
            "MID": 47.74,
            "INTERNAL_TOTAL": 66.34,
            "TOTAL": 84.94,
            "GRADE": 106.70,
            "ATTEMPT": 118.10,
        }
        self.assertEqual(set(offsets), set(expected))
        for key, value in expected.items():
            self.assertAlmostEqual(offsets[key], value, places=2)

    def test_student_offsets_preserve_two_ese_row_layout(self):
        offsets = self.parser._student_row_offsets(
            {
                "CREDIT": [143.23],
                "ESE TOTAL": [157.88, 172.53],
                "CA INTERNAL": [187.18],
                "MID INTERNAL": [201.83],
                "INT TOTAL": [216.48],
                "TOTAL": [231.13],
            }
        )

        expected = {
            "ESE_0": 10.54,
            "ESE_1": 29.14,
            "CA": 47.74,
            "MID": 66.34,
            "INTERNAL_TOTAL": 84.94,
            "TOTAL": 103.54,
            "GRADE": 125.30,
            "ATTEMPT": 136.70,
        }
        self.assertEqual(set(offsets), set(expected))
        for key, value in expected.items():
            self.assertAlmostEqual(offsets[key], value, places=2)

    def test_wrapped_subject_definition_keeps_full_name_and_credit(self):
        subjects = self.parser._parse_subject_catalog(
            "\n".join(
                (
                    "BTECPL506 : COMPUTER NETWORKS AND CLOUD COMPUTING LAB AND COMPETITIVE",
                    "PROGRAMMING LAB (Credit :2 )",
                )
            )
        )

        self.assertEqual(len(subjects), 1)
        self.assertEqual(subjects[0].code, "BTECPL506")
        self.assertEqual(
            subjects[0].name,
            "COMPUTER NETWORKS AND CLOUD COMPUTING LAB AND COMPETITIVE "
            "PROGRAMMING LAB",
        )
        self.assertEqual(str(subjects[0].credits), "2")


if __name__ == "__main__":
    unittest.main()
