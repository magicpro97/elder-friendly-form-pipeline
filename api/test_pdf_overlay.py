"""
Quick test for improved PDF overlay functionality
"""
from app.main import overlay_pdf, create_pdf_from_answers
from io import BytesIO
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter


def create_sample_pdf() -> bytes:
    """Create a simple sample PDF for testing"""
    packet = BytesIO()
    can = canvas.Canvas(packet, pagesize=letter)
    can.setFont("Helvetica-Bold", 16)
    can.drawString(100, 750, "Mẫu đơn xin việc")
    can.setFont("Helvetica", 12)
    can.drawString(100, 700, "Họ và tên: ____________________________")
    can.drawString(100, 670, "Email: ____________________________")
    can.drawString(100, 640, "Số điện thoại: ____________________________")
    can.drawString(100, 610, "Địa chỉ: ____________________________")
    can.save()
    packet.seek(0)
    return packet.read()


def test_improved_overlay():
    """Test the improved overlay function"""
    print("🧪 Testing improved PDF overlay...")
    
    # Create sample PDF
    base_pdf = create_sample_pdf()
    
    # Sample answers
    answers = {
        "full_name": "Nguyễn Văn A",
        "email": "nguyenvana@example.com",
        "phone": "0901234567",
        "address": "123 Đường ABC, Quận 1, TP.HCM"
    }
    
    # Sample form schema with bbox
    form_schema = {
        "fields": [
            {
                "id": "full_name",
                "label": "Họ và tên",
                "type": "text",
                "page": 1,
                "bbox": [230, 700, 200, 20]
            },
            {
                "id": "email",
                "label": "Email",
                "type": "email",
                "page": 1,
                "bbox": [230, 670, 200, 20]
            },
            {
                "id": "phone",
                "label": "Số điện thoại",
                "type": "tel",
                "page": 1,
                "bbox": [230, 640, 200, 20]
            },
            {
                "id": "address",
                "label": "Địa chỉ",
                "type": "text",
                "page": 1,
                "bbox": [230, 610, 200, 20]
            }
        ]
    }
    
    # Test with schema (should use bbox)
    print("✅ Testing with bbox from schema...")
    result_with_bbox = overlay_pdf(base_pdf, answers, form_schema)
    print(f"   Generated PDF with bbox: {len(result_with_bbox)} bytes")
    
    # Test without schema (should use smart fallback)
    print("✅ Testing without schema (fallback)...")
    result_without_bbox = overlay_pdf(base_pdf, answers, None)
    print(f"   Generated PDF without bbox: {len(result_without_bbox)} bytes")
    
    # Test create new PDF
    print("✅ Testing create new PDF...")
    result_new = create_pdf_from_answers(answers)
    print(f"   Generated new PDF: {len(result_new)} bytes")
    
    # Save outputs for manual inspection
    with open("/tmp/test_with_bbox.pdf", "wb") as f:
        f.write(result_with_bbox)
    print("📄 Saved: /tmp/test_with_bbox.pdf")
    
    with open("/tmp/test_without_bbox.pdf", "wb") as f:
        f.write(result_without_bbox)
    print("📄 Saved: /tmp/test_without_bbox.pdf")
    
    with open("/tmp/test_new.pdf", "wb") as f:
        f.write(result_new)
    print("📄 Saved: /tmp/test_new.pdf")
    
    print("\n✅ All tests passed! Check /tmp/*.pdf files to verify output.")


if __name__ == "__main__":
    test_improved_overlay()
