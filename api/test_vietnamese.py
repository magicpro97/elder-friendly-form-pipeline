"""Test Vietnamese characters rendering"""
from app.main import create_pdf_from_answers

# Test with full Vietnamese text
answers = {
    "ho_va_ten": "Nguyễn Văn Đức",
    "dia_chi": "123 Đường Lê Lợi, Phường Bến Thành, Quận 1, Thành phố Hồ Chí Minh",
    "email": "nguyenvanduc@gmail.com",
    "so_dien_thoai": "0901234567",
    "ngay_sinh": "15/08/1990",
    "noi_sinh": "Hà Nội, Việt Nam",
    "trinh_do": "Đại học - Cử nhân Công nghệ Thông tin",
    "kinh_nghiem": "5 năm làm việc trong lĩnh vực phát triển phần mềm",
    "ky_nang": "Python, JavaScript, React, FastAPI, MongoDB, AWS",
    "muc_tieu": "Tìm kiếm vị trí Senior Developer tại công ty công nghệ hàng đầu",
}

print("🇻🇳 Testing Vietnamese character rendering...")
pdf_bytes = create_pdf_from_answers(answers)
print(f"✅ Generated PDF: {len(pdf_bytes)} bytes")

output_path = "/tmp/vietnamese_test.pdf"
with open(output_path, "wb") as f:
    f.write(pdf_bytes)

print(f"📄 Saved to: {output_path}")
print("\n📝 Test content:")
for key, value in answers.items():
    print(f"  • {key}: {value}")

print("\n✅ Open the PDF to verify Vietnamese characters are displayed correctly!")
print(f"   Command: open {output_path}")
