import unittest
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
from obsidian_table_cleaner import clean_markdown_table_content, clean_row_columns, format_math_and_code

class TestObsidianSanitizer(unittest.TestCase):
    def test_clean_row_columns_merges_extra_pipes(self):
        # 5 columns expected. Row has 7 parts (6 pipes inside the row content if unescaped)
        row = ["Cat", "Lev", "Type", "Q", "A part 1", "A part 2", "A part 3"]
        cleaned = clean_row_columns(row, expected_cols=5)
        
        assert len(cleaned) == 5
        assert cleaned[0] == "Cat"
        assert cleaned[3] == "Q"
        assert cleaned[4] == "A part 1 \\| A part 2 \\| A part 3"
        
    def test_clean_row_removes_nan_row(self):
        row = ["NaN", "NaN", "NaN", "NaN", "NaN", "NaN"]
        assert clean_row_columns(row, 5) is None
        
    def test_format_math_absolute_value(self):
        # We replace \| with LaTeX abs
        text = "Sai số = \\|baud_thực - baud_mong_muốn\\| / baud_mong_muốn"
        formatted = format_math_and_code(text)
        assert "$\\left| baud_thực - baud_mong_muốn \\right|$" in formatted
        
    def test_format_math_multiplication(self):
        text = "baud_mong_muốn \\* 100"
        assert "\\times" in format_math_and_code(text)
        
    def test_format_bitwise_code(self):
        text = "SET: reg |= (1 << 5)."
        formatted = format_math_and_code(text)
        assert "`reg |= (1 << 5)`" in formatted
        
    def test_table_conversion(self):
        raw = (
            "| Category | Level | Type | Question | Answer |\n"
            "| --- | --- | --- | --- | --- | --- |\n"  # 6 cols
            "| NaN | NaN | NaN | NaN | NaN | NaN |\n"
            "| C | L | T | Q | reg |= (1 << 5) | Extra |"
        )
        out = clean_markdown_table_content(raw, output_mode='table')
        
        # NaN is removed
        assert "NaN" not in out
        
        # Ensure header is intact
        assert "Category" in out
        
        # Ensure code is wrapped and merged
        assert "`reg |= (1 << 5)` \\| Extra" in out
        
        # Verify columns count (count of unescaped | delimiters per line)
        import re
        for i, line in enumerate(out.splitlines()):
            # A well-formed 5 column table line has 6 pipe delimiters (ignoring \| and |=)
            unescaped_pipes = len(re.findall(r'(?<!\\)\|(?![\=])', line))
            assert unescaped_pipes == 6, f"Line {i} does not have exactly 6 delimiters: {line}"
            
    def test_callout_conversion(self):
        raw = (
            "| Category | Level | Type | Question | Answer |\n"
            "| --- | --- | --- | --- | --- |\n"
            "| UART | Adv | Scen | Sai số? | 2^(1/n) <= 5 |"
        )
        out = clean_markdown_table_content(raw, output_mode='callout')
        
        assert "> [!question] [UART - Adv] Sai số?" in out
        assert "> **Type:** `Scen`" in out
        assert "> > [!success]- Answer" in out
        assert "$2^{1/n}$ $\\le$ 5" in out

    def test_preserves_non_table_content(self):
        raw = "Header\n| A | B |\n| --- | --- |\n| 1 | 2 |\nFooter"
        out = clean_markdown_table_content(raw)
        assert "Header" in out
        assert "Footer" in out
        assert "| A | B |" in out

    def test_multiple_tables_stay_separate(self):
        raw = "| A | B |\n| --- | --- |\n| 1 | 2 |\nText\n| C | D |\n| --- | --- |\n| 3 | 4 |"
        out = clean_markdown_table_content(raw)
        assert "| 1 | 2 |" in out
        assert "Text" in out
        assert "| C | D |" in out

    def test_empty_first_cell_not_treated_as_separator(self):
        raw = "| | B | C |\n| --- | --- | --- |\n| | 2 | 3 |"
        out = clean_markdown_table_content(raw)
        lines = out.splitlines()
        # Row 3 (index 2) should be kept
        assert len(lines) >= 3
        assert "|  | 2 | 3 |" in lines[2]

    def test_callout_with_non_5_cols(self):
        raw = "| A | B |\n| --- | --- |\n| 1 | 2 |"
        out = clean_markdown_table_content(raw, output_mode='callout')
        assert "> [!note] 1" in out
        assert "> 2" in out

    def test_split_escaped_pipe(self):
        raw = "| A | B \\| C |"
        from obsidian_table_cleaner import _split_table_row
        parts = _split_table_row(raw)
        assert parts == ["A", "B \\| C"]

    def test_multiplication_regex_not_greedy(self):
        # Using a math multiplication
        out1 = format_math_and_code("1 * 2")
        assert "\\times" in out1
        # Not a math multiplication (e.g. bold or just spaces around *)
        out2 = format_math_and_code("Hello * World")
        assert "\\times" not in out2

    def test_raw_string_latex(self):
        out = format_math_and_code("<= >= ±")
        assert "$\\le$ $\\ge$ $\\pm$" in out

    def test_exponent_generalized(self):
        out = format_math_and_code("x^(a/b)")
        assert "$x^{a/b}$" in out

if __name__ == "__main__":
    unittest.main(verbosity=2)
