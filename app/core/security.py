import hashlib
import hmac
import time

ZALO_SIGNATURE_HEADER = "X-ZEvent-Signature"  # [XÁC MINH] tên header


def verify_zalo_signature(
    *,
    raw_body: bytes,
    signature_header: str | None,
    app_id: str,
    timestamp: str | int,
    oa_secret_key: str,
    max_age_seconds: int,
    now: float | None = None,
) -> bool:
    """Kiểm tra MAC của sự kiện webhook Zalo OA và độ tươi của timestamp.

    Công thức theo tài liệu Zalo (cần xác minh):
        mac = sha256(app_id + raw_body + timestamp + oa_secret_key)
    Header có dạng: "mac=<hex>".
    """
    if not signature_header or not signature_header.startswith("mac="):
        return False

    # Chống replay: timestamp của Zalo có thể là giây hoặc mili giây [XÁC MINH]
    ts = int(timestamp)
    if ts > 10**11:  # mili giây -> giây
        ts //= 1000
    current = now if now is not None else time.time()
    if abs(current - ts) > max_age_seconds:
        return False

    payload = f"{app_id}".encode() + raw_body + f"{timestamp}".encode() + oa_secret_key.encode()
    expected = hashlib.sha256(payload).hexdigest()
    received = signature_header.removeprefix("mac=").strip().lower()
    return hmac.compare_digest(expected, received)
