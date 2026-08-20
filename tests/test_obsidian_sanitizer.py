import pytest
from pathlib import Path
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "tools")))
from obsidian_table_cleaner import clean_markdown_table_content, clean_row_columns, format_math_and_code

class TestObsidianSanitizer:
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
        
        # Verify columns count (count of | characters per line)
        for i, line in enumerate(out.splitlines()):
            # A well-formed 5 column table line has 6 pipes
            assert line.count('|') == 6, f"Line {i} does not have exactly 6 pipes: {line}"
            
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

if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-v"]))
