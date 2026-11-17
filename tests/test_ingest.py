from app.services.ingestion import extract_and_chunk_pdf

chunks = extract_and_chunk_pdf("data/raw_pdfs/Triệu-chứng-bệnh-ở-nhà-thuốc.pdf")
print(f"Tổng số chunks: {len(chunks)}")
print("Mẫu chunk 50:", chunks[50])