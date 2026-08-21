import re
import sys
from typing import Tuple, List, Dict
from tools.obsidian_table_cleaner import (
    _split_table_row,
    parse_markdown_table_rows,
    clean_row_columns,
    format_math_and_code,
    convert_to_callout,
    convert_to_table
)

def _is_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith('|') and stripped.endswith('|')

def _split_into_blocks(content: str) -> List[Tuple[str, List[str]]]:
    """Tách content thành các block dạng ('table', lines) và ('text', lines)."""
    lines = content.splitlines()
    blocks = []
    current_block_type = None
    current_block_lines = []

    for line in lines:
        is_table = _is_table_line(line)
        block_type = 'table' if is_table else 'text'
        
        if current_block_type is None:
            current_block_type = block_type
            current_block_lines.append(line)
        elif current_block_type == block_type:
            current_block_lines.append(line)
        else:
            blocks.append((current_block_type, current_block_lines))
            current_block_type = block_type
            current_block_lines = [line]

    if current_block_type:
        blocks.append((current_block_type, current_block_lines))

    return blocks

def _table_header_signature(table_lines: List[str]) -> str:
    """Trả về signature của header bảng để so sánh (không phân biệt chữ hoa/thường, không tính space)."""
    for line in table_lines:
        if _is_table_line(line):
            # Header thường là dòng đầu tiên
            return line.replace(" ", "").lower()
    return ""

def _is_separator_block(text_lines: List[str]) -> bool:
    """Kiểm tra xem block text có phải chỉ là comment phân trang (<!-- Page N -->) hoặc khoảng trắng."""
    for line in text_lines:
        s = line.strip()
        if not s:
            continue
        if re.match(r'^<!--\s*Page\s+\d+\s*-->$', s):
            continue
        return False # Có text thật
    return True

def _merge_table_blocks(blocks: List[Tuple[str, List[str]]]) -> List[Tuple[str, List[str]]]:
    """Nối các block table nằm cạnh nhau bị phân cách bởi page break hoặc dòng trống."""
    merged_blocks = []
    i = 0
    n = len(blocks)
    
    while i < n:
        b_type, b_lines = blocks[i]
        
        if b_type == 'table':
            current_table_lines = list(b_lines)
            current_sig = _table_header_signature(current_table_lines)
            
            # Nhìn tới trước xem có table tiếp theo bị ngắt không
            while i + 1 < n:
                next_type, next_lines = blocks[i+1]
                
                # Nếu ngay tiếp theo là table
                if next_type == 'table':
                    next_sig = _table_header_signature(next_lines)
                    if next_sig == current_sig:
                        # Gộp, loại bỏ phần header/separator của bảng sau
                        rows, _ = parse_markdown_table_rows(next_lines)
                        # rows[0] là header, rows[1] là ---
                        if len(rows) > 2:
                            # Tái tạo lại các dòng không phải header/separator
                            for row in rows[2:]:
                                current_table_lines.append("| " + " | ".join(row) + " |")
                        i += 1
                        continue
                    else:
                        break # Bảng khác nhau
                
                # Nếu bị xen giữa bởi text separator
                elif next_type == 'text' and _is_separator_block(next_lines):
                    # Kiểm tra block sau đó có phải table cùng sig không
                    if i + 2 < n and blocks[i+2][0] == 'table':
                        next_table_lines = blocks[i+2][1]
                        next_sig = _table_header_signature(next_table_lines)
                        if next_sig == current_sig:
                            # Gộp
                            rows, _ = parse_markdown_table_rows(next_table_lines)
                            if len(rows) > 2:
                                for row in rows[2:]:
                                    current_table_lines.append("| " + " | ".join(row) + " |")
                            i += 2
                            continue
                break # Không merge được nữa
            
            merged_blocks.append(('table', current_table_lines))
        else:
            merged_blocks.append((b_type, b_lines))
        i += 1

    return merged_blocks

def _detect_suspicious_formulas(text: str) -> bool:
    """Phát hiện các vùng nghi ngờ lỗi công thức để verify Lớp 1."""
    # Pattern 1: Math unicode phổ biến bị rời rạc
    suspicious_chars = r'[√∑∫∞≈≠≤≥±]'
    if re.search(suspicious_chars, text):
        pass
    
    # Pattern 2: Dấu mũ dạng ^( số hoặc chữ ) chưa được format LaTeX
    if re.search(r'\w+\^\([\w/]+\)', text):
        return True
        
    # Pattern 3: Phép nhân * hoặc \* giữa các biến/số (thường OCR hay bị dính)
    if re.search(r'\w+\s*\\\*\s*\w+', text) or re.search(r'\b\w+\s*\*\s*\w+\b', text):
        return True
        
    # Pattern 4: Bitwise operators chưa được đặt trong code block
    if re.search(r'\b\w+\s*(?:\|=|&=|\^=)\s*', text) and '`' not in text:
        return True
        
    # Unicode superscript
    if re.search(r'[⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾ⁿ]', text):
        return True
        
    return False

def fix_table_structure(markdown_content: str, output_mode: str = 'table') -> Tuple[str, List[Dict]]:
    """
    Sửa cấu trúc bảng trong toàn bộ file markdown.
    Returns:
        (markdown_đã_sửa, danh_sách_vùng_khả_nghi)
    """
    blocks = _split_into_blocks(markdown_content)
    merged_blocks = _merge_table_blocks(blocks)
    
    output_lines = []
    suspicious_regions = []
    
    for b_type, b_lines in merged_blocks:
        if b_type == 'table':
            rows, _ = parse_markdown_table_rows(b_lines)
            if not rows:
                output_lines.extend(b_lines)
                continue
                
            expected_cols = len(rows[0])
            cleaned_rows = []
            
            for idx, row in enumerate(rows):
                # Check separator line `|---|---|`
                is_separator = bool(row[0]) and set(row[0].replace('-', '').replace(':', '')) == set()
                if is_separator:
                    if idx == 1:
                        cleaned_rows.append(row[:expected_cols])
                    continue
                
                clean_row = clean_row_columns(row, expected_cols)
                if clean_row:
                    cleaned_rows.append(clean_row)
                    
            if not cleaned_rows:
                output_lines.extend(b_lines)
                continue
                
            # Formatting
            if output_mode != 'none':
                # Hàm convert_to_table / convert_to_callout đã gọi format_math_and_code
                if output_mode == 'callout':
                    formatted_table = convert_to_callout(cleaned_rows, expected_cols)
                else:
                    formatted_table = convert_to_table(cleaned_rows, expected_cols)
                    
                output_lines.append(formatted_table)
                
                if _detect_suspicious_formulas(formatted_table):
                    suspicious_regions.append({
                        'type': 'table',
                        'content': formatted_table
                    })
            else:
                # Nếu output_mode = 'none', giữ nguyên text ban đầu nhưng cấu trúc đã chuẩn
                # Do chưa format_math_and_code, ta render thủ công
                rendered_lines = []
                for i, row in enumerate(cleaned_rows):
                    if i == 1:
                        rendered_lines.append("| " + " | ".join(["---"] * expected_cols) + " |")
                    else:
                        rendered_lines.append("| " + " | ".join(row) + " |")
                
                rendered_table = "\n".join(rendered_lines)
                output_lines.append(rendered_table)
                if _detect_suspicious_formulas(rendered_table):
                    suspicious_regions.append({
                        'type': 'table',
                        'content': rendered_table
                    })
        else:
            # text block
            text_block = "\n".join(b_lines)
            output_lines.append(text_block)
            if _detect_suspicious_formulas(text_block):
                 suspicious_regions.append({
                     'type': 'text',
                     'content': text_block
                 })

    return "\n".join(output_lines), suspicious_regions
