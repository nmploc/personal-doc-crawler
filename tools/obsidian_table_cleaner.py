import os
import re
import argparse
from pathlib import Path

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
            # Split theo | nhưng cẩn thận với | đã được escape (\|)
            # Tạm thời dùng split('|') rồi sau đó gộp lại nếu bị dư cột
            parts = [p.strip() for p in stripped.strip('|').split('|')]
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
    text = re.sub(r'(\w+)\s*\\\*\s*(\w+)', r'\1 \times \2', text)
    text = re.sub(r'(\w+)\s*\*\s*(\w+)', r'\1 \times \2', text)
    # 3. Code bitwise
    if re.search(r'(\b\w+\s*(\|=|&=|\^=|<<|>>)\s*[^A-Za-z]+)', text) and '`' not in text:
        text = re.sub(r'(\b\w+\s*(?:\|=|&=|\^=|<<|>>)\s*[^A-Za-z]+)', r'`\1`', text)
    # 4. Đặc biệt
    text = re.sub(r'2\^\(1/n\)', r'$2^{1/n}$', text)
    text = text.replace('<=', '$\le$')
    text = text.replace('>=', '$\ge$')
    text = text.replace('±', '$\pm$')
    
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

def convert_to_callout(cleaned_rows):
    lines = []
    for row in cleaned_rows[2:]:
        if len(row) < 5:
            continue
        category, level, type_, question, answer = row[:5]
        question = format_math_and_code(question)
        answer = format_math_and_code(answer)
        
        callout = f"> [!question] [{category} - {level}] {question}\n"
        callout += f"> **Type:** `{type_}`\n"
        callout += f"> \n"
        callout += f"> > [!success]- Answer\n"
        
        answer_lines = answer.split('<br>') if '<br>' in answer else [answer]
        for al in answer_lines:
            callout += f"> > {al.strip()}\n"
            
        lines.append(callout)
        lines.append("")
    return "\n".join(lines)

def clean_markdown_table_content(content: str, output_mode='table') -> str:
    """ API function to clean a markdown table string """
    lines = content.splitlines()
    rows, non_table_lines = parse_markdown_table_rows(lines)
    
    if not rows:
        return content
        
    expected_cols = len(rows[0]) if rows else 5
    
    cleaned_rows = []
    for i, row in enumerate(rows):
        if set(row[0].replace('-', '').replace(':', '')) == set():
            if i == 1:
                cleaned_rows.append(row[:expected_cols])
            continue
            
        clean_row = clean_row_columns(row, expected_cols)
        if clean_row:
            cleaned_rows.append(clean_row)
            
    if output_mode == 'callout':
        return convert_to_callout(cleaned_rows)
    else:
        return convert_to_table(cleaned_rows, expected_cols)

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
