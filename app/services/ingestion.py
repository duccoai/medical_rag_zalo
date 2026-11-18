import re
from pathlib import Path
from pypdf import PdfReader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.core.exceptions import AppBaseException


def clean_pdf_text(raw_text: str) -> str:
    """Làm sạch ký tự xuống dòng vỡ câu và khoảng trắng thừa từ file PDF"""
    # Thay thế nhiều dấu xuống dòng/tab/khoảng trắng liên tiếp (r"\s+") thành 1 dấu cách đơn
    cleaned = re.sub(r"\s+", " ", raw_text)
    # Loại bỏ khoảng trắng thừa ở đầu và cuối chuỗi
    return cleaned.strip()


def extract_and_chunk_pdf(
    pdf_path: str | Path,
    chunk_size: int = 600,       # Kích thước tối đa mỗi chunk (mặc định 600 ký tự)
    chunk_overlap: int = 100,    # Số ký tự chồng lấp giữa các chunk liền kề (mặc định 100)
) -> list[dict]:
    """Đọc từng trang PDF, làm sạch và chia thành các chunks kèm metadata"""
    
    # 1. KIỂM TRA TÍNH HỢP LỆ CỦA FILE
    file_path = Path(pdf_path)
    # Nếu file không tồn tại hoặc không phải đuôi .pdf thì ném ra ngoại lệ (exception)
    if not file_path.exists() or file_path.suffix.lower() != ".pdf":
        raise AppBaseException(
            message=f"Không tìm thấy file PDF hợp lệ tại: {file_path}",
            status_code=400,
        )

    # 2. KHỞI TẠO CÔNG CỤ ĐỌC VÀ CẮT VĂN BẢN
    # Khởi tạo đối tượng đọc file PDF bằng thư viện pypdf
    reader = PdfReader(str(file_path))
    
    # Khởi tạo bộ chia văn bản thông minh của LangChain với thứ tự ưu tiên cắt:
    # Đoạn văn (\n\n) -> Dòng mới (\n) -> Hết câu (. ) -> Khoảng trắng -> Ký tự trống
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    #(tức là sau khi cắt \n\n mà vẫn >600 thì tiếp tục cắt level \n -> . -> , ... đến khi nào <600)

    # Khởi tạo danh sách chứa kết quả và biến đếm số thứ tự chunk
    chunks_with_metadata: list[dict] = []
    chunk_index = 0

    # 3. LUỒNG XỬ LÝ CHÍNH (DUYỆT TỪNG TRANG) (trang N phải được xử lý xong xuôi từ sub_chunks thành chunks rồi mới đến trang N+1)
    # Duyệt qua từng trang của PDF, bắt đầu đếm số trang (page_num) từ 1
    for page_num, page in enumerate(reader.pages, start=1):
        # Trích xuất văn bản thô của trang, nếu trang trống thì trả về chuỗi rỗng
        raw_text = page.extract_text() or ""
        # Làm sạch văn bản vừa trích xuất
        clean_text = clean_pdf_text(raw_text)

        # LỌC TRANG RÁC: Bỏ qua các trang trống hoặc trang bìa có ít hơn 50 ký tự
        if len(clean_text) < 50:
            continue

        # CẮT NHỎ VĂN BẢN: Băm nội dung trang thành các đoạn nhỏ (sub_chunks) tuân thủ chunk_size
        sub_chunks = text_splitter.split_text(clean_text)
        ## lúc này sub_chunks cơ bản tương tự chunks (chỉ là chưa được gắn metadata, lưu tạm thời trên RAM dưới dạng str, nên cần gắn metadata -> chunks rồi đóng gói -> Object -> lưu vào chunks_with_metadata)


        # 4. GẮN METADATA VÀ LƯU TRỮ
        for chunk in sub_chunks:
            # fix lỗi dính dấu chấm/ phẩy thừa ở đầu chunk
            fixed_chunk = re.sub(r"^[\.\,\;\:\s]+", "", chunk).strip()
            if not fixed_chunk:
                continue

            chunks_with_metadata.append(
                {
                    "content": fixed_chunk,  # Nội dung văn bản của chunk
                    "metadata": {
                        "source": file_path.name,  # Tên file nguồn
                        "page": page_num,          # Số trang chứa chunk này
                        "chunk_index": chunk_index,# Thứ tự toàn cục của chunk trong tài liệu
                    },
                }
            )
            # Tăng biến đếm index cho chunk tiếp theo
            chunk_index += 1

    # Trả về danh sách các chunks hoàn chỉnh kèm metadata sẵn sàng đưa vào Vector DB
    return chunks_with_metadata