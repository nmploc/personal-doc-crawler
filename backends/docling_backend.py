import subprocess
import tempfile
from pathlib import Path
from config import DOCLING_CMD


def parse_with_docling(input_path: Path) -> str:
    """Chạy CLI docling, xuất markdown ra thư mục tạm rồi đọc lại."""
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        result = subprocess.run(
            [
                DOCLING_CMD,
                str(input_path),
                "--to",
                "md",
                "--output",
                str(tmp_path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(f"docling lỗi: {result.stderr.strip()}")

        md_files = list(tmp_path.glob("*.md"))
        if not md_files:
            raise RuntimeError("docling không sinh ra file markdown nào.")

        return md_files[0].read_text(encoding="utf-8")
