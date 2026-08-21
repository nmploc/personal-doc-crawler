import os
import sys
import re
import argparse
from pathlib import Path

if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

def _split_table_row(stripped: str) -> list[str]:
    """Split theo | nhưng bỏ qua \| đã escape và |= (toán tử bitwise)."""
    inner = stripped.strip('|')
    # Regex split trên | không đứng ngay sau backslash và không đứng trước =
    parts = re.split(r'(?<!\\)\|(?![\=])', inner)
    return [p.strip() for p in parts]

def parse_markdown_table_rows(lines):
    """
    Tách các dòng của bảng Markdown (bắt đầu bằng |)
    Trả về danh sách các list string (các cột) và các dòng không phải bảng.
    """
    rows = []
    non_table_lines = []
    in_table = False
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('|') and stripped.endswith('|'):
            in_table = True
            parts = _split_table_row(stripped)
            rows.append(parts)
        else:
            if in_table:
                in_table = False
            non_table_lines.append(line)
            
    return rows, non_table_lines

def clean_row_columns(row_parts, expected_cols=5):
    """
    Nếu một dòng có nhiều hơn expected_cols, gom các cột thừa vào cột cuối cùng.
    Ví dụ: ['UART', 'Advanced', 'Scenario', 'Question', 'Ans1', 'Ans2', 'Ans3']
    sẽ gộp Ans1, Ans2, Ans3 thành Ans1 \| Ans2 \| Ans3
    """
    if all('NaN' in str(p) or not p for p in row_parts):
        return None
        
    if len(row_parts) > expected_cols:
        clean_row = row_parts[:expected_cols - 1]
        last_col = ' \\| '.join(row_parts[expected_cols - 1:])
        clean_row.append(last_col)
        return clean_row
    
    while len(row_parts) < expected_cols:
        row_parts.append("")
        
    return row_parts

def format_math_and_code(text):
    """
    Chuẩn hóa các đoạn mã và công thức toán học cho Obsidian.
    """
    if not text:
        return text
    
    # 1. Mathjax Abs
    text = re.sub(r'\\\|([^\|]+?)\\\|', r'$\\left| \1 \\right|$', text)
    # 2. Xử lý nhân
    # Phép nhân có escape \* (MarkItDown / Excel export)
    text = re.sub(r'(\w+)\s*\\\*\s*(\w+)', r'$\1 \\times \2$', text)
    # Phép nhân thường * (chỉ áp dụng cho số hoặc biến số)
    text = re.sub(r'\b(\d+)\s*\*\s*(\d+)\b', r'$\1 \\times \2$', text)
    text = re.sub(r'\b([a-zA-Z_]\w*)\s*\*\s*(\d+)\b', r'$\1 \\times \2$', text)
    text = re.sub(r'\b(\d+)\s*\*\s*([a-zA-Z_]\w*)\b', r'$\1 \\times \2$', text)
    # 3. Code bitwise
    bitwise_pattern = r'(\b\w+\s*(?:\|=|&=|\^=)\s*(?:\([^\\\|`\n\.,;]+\)|[0-9a-zA-Z_~]+)|\b\w+\s*(?:<<|>>)\s*\d+)'
    if '`' not in text and re.search(bitwise_pattern, text):
        text = re.sub(bitwise_pattern, r'`\1`', text)
    # 4. Đặc biệt
    text = re.sub(r'(\w+)\^\((\w+)/(\w+)\)', r'$\1^{\2/\3}$', text)
    text = text.replace('<=', r'$\le$')
    text = text.replace('>=', r'$\ge$')
    text = text.replace('±', r'$\pm$')
    
    # Sửa underscore trong math (baud_thực -> \text{baud}_\text{thực})
    # Cái này khá phức tạp nếu làm bằng regex đơn giản, tạm thời để Obsidian handle hoặc thêm regex
    
    return text

def convert_to_table(cleaned_rows, expected_cols):
    lines = []
    for i, row in enumerate(cleaned_rows):
        if i == 1:
            lines.append("| " + " | ".join(["---"] * expected_cols) + " |")
        else:
            formatted_row = [format_math_and_code(cell) for cell in row]
            lines.append("| " + " | ".join(formatted_row) + " |")
    return "\n".join(lines)

def convert_to_callout(cleaned_rows, expected_cols):
    lines = []
    for row in cleaned_rows[2:]:
        if len(row) < expected_cols:
            continue
            
        # Chỉ áp dụng schema Q&A khi đúng 5 cột — với schema khác, in dạng key: value chung
        if expected_cols == 5:
            category, level, type_, question, answer = row[:5]
            callout = f"> [!question] [{category} - {level}] {format_math_and_code(question)}\n"
            callout += f"> **Type:** `{type_}`\n> \n> > [!success]- Answer\n"
            answer_text = format_math_and_code(answer)
            for al in (answer_text.split('<br>') if '<br>' in answer_text else [answer_text]):
                callout += f"> > {al.strip()}\n"
        else:
            # Fallback tổng quát: in mọi cột dưới dạng callout key:value
            callout = f"> [!note] {row[0]}\n"
            for cell in row[1:]:
                callout += f"> {format_math_and_code(cell)}\n"

        lines.append(callout)
        lines.append("")
    return "\n".join(lines)

def _clean_rows(rows, expected_cols):
    """Tách riêng phần logic lọc/clean rows để tái sử dụng."""
    cleaned_rows = []
    for idx, row in enumerate(rows):
        is_separator = bool(row[0]) and set(row[0].replace('-', '').replace(':', '')) == set()
        if is_separator:
            if idx == 1:
                cleaned_rows.append(row[:expected_cols])
            continue
        clean_row = clean_row_columns(row, expected_cols)
        if clean_row:
            cleaned_rows.append(clean_row)
    return cleaned_rows

def clean_markdown_table_content(content: str, output_mode='table') -> str:
    """
    Duyệt qua từng dòng, giữ nguyên nội dung không phải bảng,
    chỉ làm sạch riêng từng khối bảng markdown tìm thấy.
    """
    lines = content.splitlines()
    output_lines = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if stripped.startswith('|') and stripped.endswith('|'):
            # Bắt đầu một khối bảng — thu thập liên tục cho đến khi hết dòng bảng
            table_block_lines = []
            while i < n:
                s = lines[i].strip()
                if s.startswith('|') and s.endswith('|'):
                    table_block_lines.append(lines[i])
                    i += 1
                else:
                    break

            rows, _ = parse_markdown_table_rows(table_block_lines)
            if not rows:
                output_lines.extend(table_block_lines)
                continue

            expected_cols = len(rows[0]) if rows else 5
            cleaned_rows = _clean_rows(rows, expected_cols)

            if output_mode == 'callout':
                output_lines.append(convert_to_callout(cleaned_rows, expected_cols))
            else:
                output_lines.append(convert_to_table(cleaned_rows, expected_cols))
        else:
            output_lines.append(line)
            i += 1

    return "\n".join(output_lines)

def process_file(input_path, output_mode='table'):
    input_path = Path(input_path)
    if not input_path.exists():
        print(f"File không tồn tại: {input_path}")
        return
        
    with open(input_path, 'r', encoding='utf-8') as f:
        content = f.read()
        
    result = clean_markdown_table_content(content, output_mode)
        
    suffix = "_callout" if output_mode == 'callout' else "_clean"
    output_path = input_path.with_name(f"{input_path.stem}{suffix}.md")
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(result)
        
    print(f"Đã lưu kết quả tại: {output_path}")
    return output_path

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Làm sạch bảng Markdown từ Excel cho Obsidian")
    parser.add_argument("input_file", help="Đường dẫn đến file markdown cần làm sạch")
    parser.add_argument("--mode", choices=['table', 'callout'], default='table', help="Định dạng xuất (mặc định: table)")
    args = parser.parse_args()
    
    process_file(args.input_file, args.mode)
