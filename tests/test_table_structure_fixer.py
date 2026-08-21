import unittest
from tools.table_structure_fixer import (
    _split_into_blocks,
    _table_header_signature,
    _merge_table_blocks,
    fix_table_structure
)

class TestTableStructureFixer(unittest.TestCase):
    def test_single_table_no_change(self):
        markdown = (
            "| Header 1 | Header 2 |\n"
            "|---|---|\n"
            "| A | B |\n"
        )
        output, _ = fix_table_structure(markdown, output_mode='none')
        self.assertEqual(output.strip(), markdown.strip())

    def test_merge_page_break_comment(self):
        markdown = (
            "| Col1 | Col2 |\n"
            "|---|---|\n"
            "| Data1 | Data2 |\n"
            "\n"
            "<!-- Page 2 -->\n"
            "\n"
            "| Col1 | Col2 |\n"
            "|---|---|\n"
            "| Data3 | Data4 |\n"
        )
        expected = (
            "| Col1 | Col2 |\n"
            "| --- | --- |\n"
            "| Data1 | Data2 |\n"
            "| Data3 | Data4 |"
        )
        output, _ = fix_table_structure(markdown, output_mode='none')
        self.assertEqual(output.strip(), expected)
        
    def test_merge_blank_line(self):
        markdown = (
            "| ID | Name |\n"
            "|---|---|\n"
            "| 1 | Alice |\n"
            "\n"
            "\n"
            "| ID | Name |\n"
            "|---|---|\n"
            "| 2 | Bob |\n"
        )
        expected = (
            "| ID | Name |\n"
            "| --- | --- |\n"
            "| 1 | Alice |\n"
            "| 2 | Bob |"
        )
        output, _ = fix_table_structure(markdown, output_mode='none')
        self.assertEqual(output.strip(), expected)

    def test_merge_three_tables_chained(self):
        markdown = (
            "| ID | Name |\n"
            "|---|---|\n"
            "| 1 | Alice |\n"
            "\n"
            "<!-- Page 2 -->\n"
            "| ID | Name |\n"
            "|---|---|\n"
            "| 2 | Bob |\n"
            "\n"
            "| ID | Name |\n"
            "|---|---|\n"
            "| 3 | Charlie |\n"
        )
        expected = (
            "| ID | Name |\n"
            "| --- | --- |\n"
            "| 1 | Alice |\n"
            "| 2 | Bob |\n"
            "| 3 | Charlie |"
        )
        output, _ = fix_table_structure(markdown, output_mode='none')
        self.assertEqual(output.strip(), expected)

    def test_independent_tables_not_merged(self):
        markdown = (
            "| ID | Name |\n"
            "|---|---|\n"
            "| 1 | Alice |\n"
            "\n"
            "<!-- Page 2 -->\n"
            "\n"
            "| UUID | Score |\n"
            "|---|---|\n"
            "| a-1 | 90 |\n"
        )
        expected = (
            "| ID | Name |\n"
            "| --- | --- |\n"
            "| 1 | Alice |\n"
            "\n"
            "<!-- Page 2 -->\n"
            "\n"
            "| UUID | Score |\n"
            "| --- | --- |\n"
            "| a-1 | 90 |"
        )
        output, _ = fix_table_structure(markdown, output_mode='none')
        self.assertEqual(output.strip(), expected)

    def test_column_normalization(self):
        # Expected cols based on the header is 3
        markdown = (
            "| H1 | H2 | H3 |\n"
            "|---|---|---|\n"
            "| A | B | C | D | E |\n"  # 5 cols, should merge C, D, E
            "| A | B |\n"  # 2 cols, should pad with empty
        )
        expected = (
            "| H1 | H2 | H3 |\n"
            "| --- | --- | --- |\n"
            "| A | B | C \\| D \\| E |\n"
            "| A | B |  |"
        )
        output, _ = fix_table_structure(markdown, output_mode='none')
        self.assertEqual(output.strip(), expected)

    def test_preserves_text_between_tables(self):
        markdown = (
            "| H1 | H2 |\n"
            "|---|---|\n"
            "| A | B |\n"
            "\n"
            "Some intermediate text here.\n"
            "\n"
            "| H1 | H2 |\n"
            "|---|---|\n"
            "| C | D |\n"
        )
        expected = (
            "| H1 | H2 |\n"
            "| --- | --- |\n"
            "| A | B |\n"
            "\n"
            "Some intermediate text here.\n"
            "\n"
            "| H1 | H2 |\n"
            "| --- | --- |\n"
            "| C | D |"
        )
        output, _ = fix_table_structure(markdown, output_mode='none')
        self.assertEqual(output.strip(), expected)
        
    def test_format_math_integrated(self):
        markdown = (
            "| H1 | H2 |\n"
            "|---|---|\n"
            "| <= | a \\* b |\n"
        )
        expected = (
            "| H1 | H2 |\n"
            "| --- | --- |\n"
            "| $\\le$ | $a \\times b$ |"
        )
        output, _ = fix_table_structure(markdown, output_mode='table')
        self.assertEqual(output.strip(), expected)

if __name__ == '__main__':
    unittest.main()
