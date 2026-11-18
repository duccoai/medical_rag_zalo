import re
from collections import Counter
from pathlib import Path

import pymupdf4llm
from langchain_text_splitters import (
    MarkdownHeaderTextSplitter,
    RecursiveCharacterTextSplitter,
)

from app.core.exceptions import AppBaseException

# Tầng 1 (cấu trúc): cấp tiêu đề cần băm. Key là tên trường lưu trong metadata "headers".
HEADERS_TO_SPLIT_ON = [
    ("#", "h1"),
    ("##", "h2"),
    ("###", "h3"),
]
HEADER_KEYS = [key for _, key in HEADERS_TO_SPLIT_ON]

# Dòng không phải tiêu đề, ngắn, lặp lại từ REPEAT_THRESHOLD lần trở lên được coi là header/footer chạy trang
REPEAT_THRESHOLD = 5
REPEAT_MAX_LENGTH = 80

# Số trang đứng riêng một dòng: "12", "- 12 -", "Trang 12", "12/120", "Trang 12/120"
PAGE_NUMBER_PATTERN = re.compile(
    r"^[\-–—\s]*(?:trang\s*)?\d{1,4}(?:\s*/\s*\d{1,4})?[\-–—\s]*$",
    re.IGNORECASE,
)
HEADING_PATTERN = re.compile(r"^#{1,6}\s")
EMPHASIS_PATTERN = re.compile(r"[*_`]+")
BLANK_LINES_PATTERN = re.compile(r"\n{3,}")
LEADING_PUNCTUATION_PATTERN = re.compile(r"^[\.\,\;\:\s]+")


def _is_repeat_candidate(line: str) -> bool:
    """Dòng văn bản thường (không phải heading, bảng) đủ ngắn để có thể là header/footer"""
    stripped = line.strip()
    return (
        bool(stripped)
        and not HEADING_PATTERN.match(stripped)
        and not stripped.startswith("|")
        and len(stripped) <= REPEAT_MAX_LENGTH
    )


def clean_markdown_text(markdown: str) -> str:
    """Lọc nhẹ Markdown: bỏ header/footer lặp lại và số trang đứng riêng, giữ nguyên tiêu đề và nội dung"""
    lines = [line.rstrip() for line in markdown.splitlines()]

    # Đếm số lần xuất hiện của từng dòng ứng viên header/footer (so khớp theo chữ thường, bỏ khoảng trắng thừa)
    candidate_counts = Counter(
        " ".join(line.split()).lower() for line in lines if _is_repeat_candidate(line)
    )
    repeated_lines = {
        text for text, count in candidate_counts.items() if count >= REPEAT_THRESHOLD
    }

    kept_lines: list[str] = []
    for line in lines:
        stripped = line.strip()
        if PAGE_NUMBER_PATTERN.match(stripped):
            continue
        if _is_repeat_candidate(line) and " ".join(stripped.split()).lower() in repeated_lines:
            continue
        kept_lines.append(line)

    cleaned = "\n".join(kept_lines)
    return BLANK_LINES_PATTERN.sub("\n\n", cleaned).strip()


def pdf_to_markdown(pdf_path: Path) -> str:
    """Chuyển toàn bộ PDF thành một chuỗi Markdown liền mạch, không tách theo trang"""
    try:
        return pymupdf4llm.to_markdown(str(pdf_path))
    except Exception as ex:
        raise AppBaseException(
            message=f"Không thể đọc nội dung file PDF: {ex}",
            status_code=422,
        ) from ex


def _clean_header_text(text: str) -> str:
    """Bỏ ký tự định dạng Markdown (*, _, `) còn sót trong tên tiêu đề"""
    return " ".join(EMPHASIS_PATTERN.sub("", text).split())


def _build_breadcrumb(headers: dict[str, str]) -> str:
    """Nối chuỗi phân cấp tiêu đề: 'Header 1 > Header 2 > Header 3'"""
    return " > ".join(headers[key] for key in HEADER_KEYS if headers.get(key))


def _with_breadcrumb(headers: dict[str, str], body: str) -> str:
    """Gắn breadcrumb vào đầu nội dung chunk để ngữ cảnh tiêu đề đi cùng văn bản khi embedding"""
    breadcrumb = _build_breadcrumb(headers)
    if not breadcrumb:
        return f"Nội dung: {body}"
    return f"Tiêu đề: {breadcrumb}\nNội dung: {body}"


def chunk_markdown(
    markdown: str,
    source: str,
    chunk_size: int = 600,
    chunk_overlap: int = 100,
) -> list[dict]:
    """Băm Markdown hai tầng: theo tiêu đề (tầng 1), rồi đệ quy theo độ dài (tầng 2)"""
    header_splitter = MarkdownHeaderTextSplitter(
        headers_to_split_on=HEADERS_TO_SPLIT_ON,
        strip_headers=True,
    )
    body_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: list[dict] = []
    chunk_index = 0

    # TẦNG 1: mỗi section có một bộ headers (h1/h2/h3) đúng với vị trí của nó trong tài liệu
    for section in header_splitter.split_text(markdown):
        section_headers = {
            key: _clean_header_text(value)
            for key, value in section.metadata.items()
            if key in HEADER_KEYS and value
        }

        # TẦNG 2: băm đệ quy phần vượt giới hạn; mọi sub-chunk đều được merge lại metadata/headers của section cha
        for body in body_splitter.split_text(section.page_content):
            body = LEADING_PUNCTUATION_PATTERN.sub("", body).strip()
            if not body:
                continue

            chunks.append(
                {
                    "content": _with_breadcrumb(section_headers, body),
                    "metadata": {
                        "source": source,                   # Tên file PDF nguồn
                        "chunk_index": chunk_index,         # Thứ tự toàn cục của chunk trong tài liệu
                        "headers": dict(section_headers),   # Headers kế thừa từ tầng 1 (h1/h2/h3)
                    },
                }
            )
            chunk_index += 1

    return chunks


def extract_and_chunk_pdf(
    pdf_path: str | Path,
    chunk_size: int = 600,       # Kích thước tối đa mỗi đoạn văn bản (mặc định 600 ký tự)
    chunk_overlap: int = 100,    # Số ký tự chồng lấp giữa các chunk liền kề (mặc định 100)
) -> list[dict]:
    """Đọc PDF thành Markdown liền mạch, làm sạch, băm 2 tầng và trả về danh sách chunk kèm metadata"""

    # 1. KIỂM TRA TÍNH HỢP LỆ CỦA FILE
    file_path = Path(pdf_path)
    if not file_path.exists() or file_path.suffix.lower() != ".pdf":
        raise AppBaseException(
            message=f"Không tìm thấy file PDF hợp lệ tại: {file_path}",
            status_code=400,
        )

    # 2. PDF -> MARKDOWN TOÀN CỤC (một chuỗi duy nhất, giữ header xuyên suốt các trang)
    markdown = pdf_to_markdown(file_path)

    # 3. LÀM SẠCH NHẸ TRƯỚC KHI BĂM
    cleaned_markdown = clean_markdown_text(markdown)
    if not cleaned_markdown:
        return []

    # 4. BĂM HAI TẦNG + GẮN BREADCRUMB + METADATA
    return chunk_markdown(
        cleaned_markdown,
        source=file_path.name,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
