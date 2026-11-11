from pathlib import Path

# Danh sách tất cả file và thư mục từ JSON
STRUCTURE = [
    "app",
    "app/__init__.py",
    "app/main.py",
    "app/core/__init__.py",
    "app/core/config.py",
    "app/core/security.py",
    "app/core/logging.py",
    "app/schemas/__init__.py",
    "app/schemas/medical_schema.py",
    "app/schemas/zalo_schema.py",
    "app/services/__init__.py",
    "app/services/document_processor.py",
    "app/services/embedding_service.py",
    "app/services/rag_engine.py",
    "app/vectorstore/__init__.py",
    "app/vectorstore/pgvector_store.py",
    "app/cache/__init__.py",
    "app/cache/redis_cache.py",
    "api/__init__.py",
    "api/v1/__init__.py",
    "api/v1/router.py",
    "api/v1/zalo_webhook.py",
    "data/__init__.py",
    "data/medical_docs/",
    "tests/__init__.py",
    "tests/test_schemas.py",
    "tests/test_rag_engine.py",
    "tests/test_zalo_webhook.py",
    ".env.example",
    ".env",
    "Dockerfile",
    "docker-compose.yml",
    "requirements.txt",
    "README.md",
]


def create_project_structure():
    base_dir = Path(__file__).parent.resolve()

    for item in STRUCTURE:
        path = base_dir / item
        # Nếu đường dẫn kết thúc bằng / hoặc không có đuôi file (suffix) thì tạo thư mục
        if item.endswith("/") or item.endswith("\\") or not path.suffix:
            path.mkdir(parents=True, exist_ok=True)
            print(f"[DIR]  {item}")
        else:
            # Tạo thư mục cha trước nếu chưa có, sau đó tạo file trống
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch(exist_ok=True)
            print(f"[FILE] {item}")

    print("\n✅ Đã tạo thành công toàn bộ cấu trúc dự án!")


if __name__ == "__main__":
    create_project_structure()