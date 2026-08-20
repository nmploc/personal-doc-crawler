import subprocess
from pathlib import Path
from config import MARKITDOWN_CMD


def parse_with_markitdown(input_path: Path, obsidian_mode: str = 'table') -> str:
    """Chạy MarkItDown (qua Python API hoặc CLI), trả về nội dung markdown dạng string."""
    text = ""
    # Cách 1: Thử dùng Python API trực tiếp (nhanh hơn, không bị lỗi subprocess/encoding)
    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        result = md.convert(str(input_path))
        if result and result.text_content:
            text = result.text_content
    except Exception:
        text = ""

    # Cách 2: Nếu Python API không trả kết quả, gọi qua CLI subprocess
    if not text:
        result = subprocess.run(
            [MARKITDOWN_CMD, str(input_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=180,
        )
        if result.returncode != 0:
            raise RuntimeError(f"markitdown lỗi: {result.stderr.strip()}")
        text = result.stdout

    # markitdown dựa trên pdfminer, không OCR — phát hiện lỗi font CID phổ biến
    if "(cid:" in text[:2000]:
        raise RuntimeError(
            "Phát hiện PDF dùng font CID không giải mã được — "
            "hãy dùng backend docling hoặc gemini thay vì markitdown."
        )
        
    # Hậu xử lý (Post-Processor): Làm sạch bảng Markdown cho Obsidian nếu là file Office/CSV
    if obsidian_mode != 'none' and input_path.suffix.lower() in {'.xlsx', '.xls', '.csv', '.docx'}:
        try:
            import sys
            import os
            tools_dir = str(Path(__file__).parent.parent / 'tools')
            if tools_dir not in sys.path:
                sys.path.append(tools_dir)
            from obsidian_table_cleaner import clean_markdown_table_content
            text = clean_markdown_table_content(text, output_mode=obsidian_mode)
        except Exception as e:
            print(f"[Cảnh báo] Lỗi khi làm sạch Markdown cho Obsidian: {e}")
            
    return text
