import unittest

from bizfactcheck.normalize import compare_values


class CompareValuesTests(unittest.TestCase):
    def test_money_scales_and_decimal_values_are_equivalent(self):
        pairs = [
            ("CNY 1.2 million", "120万元"),
            ("人民币 1亿元", "CNY 100 million"),
            ("USD 1 billion", "1,000 million dollars"),
            ("1.25 thousand USD", "USD 1,250"),
            ("0.30 元", "CNY 0.3"),
            ("RMB 0", "0万元"),
            ("USD -1.25 million", "-1,250,000 dollars"),
        ]
        for source, draft in pairs:
            with self.subTest(source=source, draft=draft):
                self.assertEqual(compare_values(source, draft),
                                 ("match", "equivalent_value"))

    def test_money_difference_is_a_conflict(self):
        self.assertEqual(compare_values("CNY 1.2 million", "CNY 120 million"),
                         ("conflict", "different_value"))

    def test_different_currencies_need_review_without_conversion(self):
        self.assertEqual(compare_values("CNY 100", "USD 100"),
                         ("review", "currency_mismatch"))

    def test_duration_scales_preserve_calendar_units(self):
        for source, draft in [("2 hours", "120分钟"), ("2 days", "48 hours"),
                              ("2 years", "24个月"), ("0 hours", "0 days")]:
            with self.subTest(source=source):
                self.assertEqual(compare_values(source, draft, "duration"),
                                 ("match", "equivalent_value"))
        self.assertEqual(compare_values("1 month", "30 days", "duration"),
                         ("review", "unit_mismatch"))
        self.assertEqual(compare_values("12 months", "24 months"),
                         ("conflict", "different_value"))

    def test_percent_and_percentage_points_remain_distinct(self):
        for source, draft in [("5%", "5 percent"), ("5 percentage points", "5个百分点")]:
            with self.subTest(source=source):
                self.assertEqual(compare_values(source, draft, "percentage"),
                                 ("match", "equivalent_value"))
        self.assertEqual(compare_values("5%", "5 pp"),
                         ("review", "unit_mismatch"))
        self.assertEqual(compare_values("5%", "6%"),
                         ("conflict", "different_value"))

    def test_calendar_period_equivalents(self):
        for source, draft in [("2025", "2025年度"), ("H1 2025", "2025年上半年"),
                              ("2025 H2", "2025年下半年"),
                              ("2025 Q2", "2025年第二季度")]:
            with self.subTest(source=source):
                self.assertEqual(compare_values(source, draft, "period"),
                                 ("match", "equivalent_value"))

    def test_half_year_is_not_a_full_year_or_another_year(self):
        self.assertEqual(compare_values("2025 H1", "2025"),
                         ("conflict", "different_value"))
        self.assertEqual(compare_values("2025 Q1", "2026 Q1"),
                         ("conflict", "different_value"))

    def test_project_stages_match_aliases_and_review_changes(self):
        for source, draft in [("planned", "计划中"), ("prototype", "原型"),
                              ("pilot", "试点"), ("deployed", "已部署"),
                              ("accepted", "已验收")]:
            with self.subTest(source=source):
                self.assertEqual(compare_values(source, draft, "status"),
                                 ("match", "equivalent_value"))
        self.assertEqual(compare_values("pilot", "deployed"),
                         ("review", "stage_changed"))

    def test_qualifiers_and_inequalities_never_disappear(self):
        for source, draft in [("about CNY 1 million", "CNY 1 million"),
                              ("不超过100万元", "100万元"),
                              ("<= 12 months", "12 months"),
                              ("at least 5%", "5%"),
                              ("约100万元", "约100万元")]:
            with self.subTest(source=source):
                self.assertEqual(compare_values(source, draft),
                                 ("review", "qualified_value"))

    def test_unsupported_or_ambiguous_numeric_forms_never_match(self):
        for value in ["$1 million", "1m", "1,20 USD", "CNY NaN", "CNY Infinity",
                      "2025-01-01", "FY2025", "1-2 hours", "42"]:
            with self.subTest(value=value):
                self.assertEqual(compare_values(value, value),
                                 ("review", "unsupported_value"))

    def test_wrong_explicit_kind_or_partial_parse_needs_review(self):
        self.assertEqual(compare_values("CNY 100", "CNY 100 extra", "money"),
                         ("review", "unsupported_value"))
        self.assertEqual(compare_values("pilot", "pilot", "money"),
                         ("review", "unsupported_value"))
        self.assertEqual(compare_values("CNY 100", "100 hours"),
                         ("review", "type_mismatch"))

    def test_text_changes_require_review_and_formatting_can_match(self):
        self.assertEqual(compare_values("Consulting  only", " consulting only ", "text"),
                         ("match", "equal_text"))
        self.assertEqual(compare_values("Consulting only", "Consulting and hosting"),
                         ("review", "text_changed"))
        self.assertEqual(compare_values("", ""), ("review", "missing_value"))

    def test_invalid_kind_is_an_input_error(self):
        with self.assertRaises(ValueError):
            compare_values("A", "A", "invented")

    def test_numeric_compatibility_characters_are_not_silently_flattened(self):
        for source, draft in [("USD 10⁶", "USD 106"), ("2³ hours", "23 hours"),
                              ("USD 10₆", "USD 106"), ("USD ①", "USD 1"),
                              ("USD 𝟙𝟘", "USD 10")]:
            with self.subTest(source=source):
                self.assertEqual(compare_values(source, draft), ("review", "unsupported_value"))
                self.assertEqual(compare_values(draft, source), ("review", "unsupported_value"))

    def test_fullwidth_decimal_digits_and_symbols_remain_supported(self):
        for source, draft in [("ＵＳＤ １２３．４５", "USD 123.45"),
                              ("－１２０万元", "CNY -1.2 million"),
                              ("２４ 小时", "1 day")]:
            with self.subTest(source=source):
                self.assertEqual(compare_values(source, draft), ("match", "equivalent_value"))


if __name__ == "__main__":
    unittest.main()
