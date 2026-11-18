from app.services.ingestion import clean_pdf_text, extract_doc_title, is_running_header_line


def test_running_footer_with_page_number_is_removed():
    raw = "Nội dung đoạn một\nNhịp cầu Dược lâm sàng Page 1/19\nNội dung đoạn hai"
    assert clean_pdf_text(raw) == "Nội dung đoạn một Nội dung đoạn hai"


def test_running_header_before_title_is_removed():
    raw = "Nhịp cầu Dược lâm sàng Page 2/19\n\nBÀI 1. PHƯƠNG PHÁP TƯ VẤN\nMỗi ngày mọi người"
    assert clean_pdf_text(raw) == "BÀI 1. PHƯƠNG PHÁP TƯ VẤN Mỗi ngày mọi người"


def test_standalone_page_number_line_is_removed():
    raw = "Nội dung chính\nPage 3/19\nTiếp tục"
    assert clean_pdf_text(raw) == "Nội dung chính Tiếp tục"


def test_header_keyword_without_page_number_is_removed():
    assert is_running_header_line("Nhịp cầu Dược lâm sàng")


def test_normal_line_is_not_treated_as_header():
    assert not is_running_header_line("Nhịp cầu là một cây cầu lớn trong thành phố")


def test_doc_title_skips_running_header():
    raw = "Nhịp cầu Dược lâm sàng Page 2/19\nBÀI 2. CẢM (COLD) VÀ CÖM (FLU)\nNội dung"
    assert extract_doc_title(raw, page_num=5) == "BÀI 2. CẢM (COLD) VÀ CÖM (FLU)"


def test_doc_title_falls_back_when_page_has_only_header():
    raw = "Nhịp cầu Dược lâm sàng Page 4/19\n"
    assert extract_doc_title(raw, page_num=7) == "Trang 7"
