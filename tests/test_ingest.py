from app.services.ingestion import (
    chunk_markdown,
    clean_markdown_text,
    extract_and_chunk_pdf,
)

SAMPLE_PDF = "data/raw_pdfs/Triệu-chứng-bệnh-ở-nhà-thuốc.pdf"


def test_clean_markdown_text_removes_running_lines_and_page_numbers():
    lines = []
    for i in range(6):
        lines += ["Tài liệu nhà thuốc", f"Nội dung đoạn số {i}.", f"Trang {i + 1}"]
    cleaned = clean_markdown_text("\n".join(lines))

    assert "Tài liệu nhà thuốc" not in cleaned
    assert "Trang 1" not in cleaned
    assert "Nội dung đoạn số 0." in cleaned


def test_chunk_markdown_inherits_headers_and_builds_breadcrumb():
    long_body = "Đoạn văn dài. " * 200
    markdown = (
        "# Chương 1\n"
        "Giới thiệu ngắn.\n\n"
        "## Mục A\n"
        f"{long_body}\n\n"
        "### Mục A.1\n"
        "Nội dung ngắn."
    )

    chunks = chunk_markdown(markdown, source="demo.pdf", chunk_size=600, chunk_overlap=100)

    assert len(chunks) > 2
    assert [c["metadata"]["chunk_index"] for c in chunks] == list(range(len(chunks)))
    assert all(c["metadata"]["source"] == "demo.pdf" for c in chunks)

    # Các sub-chunk của Mục A phải kế thừa đủ headers từ tầng 1
    mục_a_chunks = [
        c for c in chunks
        if c["metadata"]["headers"].get("h2") == "Mục A" and "h3" not in c["metadata"]["headers"]
    ]
    assert len(mục_a_chunks) >= 2
    assert all(c["metadata"]["headers"]["h1"] == "Chương 1" for c in mục_a_chunks)
    assert all(c["content"].startswith("Tiêu đề: Chương 1 > Mục A\nNội dung: ") for c in mục_a_chunks)

    last = chunks[-1]
    assert last["content"] == "Tiêu đề: Chương 1 > Mục A > Mục A.1\nNội dung: Nội dung ngắn."


def test_extract_and_chunk_pdf():
    chunks = extract_and_chunk_pdf(SAMPLE_PDF)

    assert len(chunks) > 0
    assert all(c["content"].startswith(("Tiêu đề: ", "Nội dung: ")) for c in chunks)
    assert all(c["metadata"]["source"] == "Triệu-chứng-bệnh-ở-nhà-thuốc.pdf" for c in chunks)
    assert [c["metadata"]["chunk_index"] for c in chunks] == list(range(len(chunks)))

# === THÊM ĐOẠN PRINT NÀY ĐỂ XEM KẾT QUẢ TRỰC QUAN ===
    print(f"\n👉 Tổng số chunks trích xuất được từ PDF thực tế: {len(chunks)}")
    if len(chunks) > 50:
        print(f"\n🔍 Mẫu chunk 50:\n{chunks[100]}")
    else:
        print(f"\n🔍 Mẫu chunk cuối:\n{chunks[-1]}")