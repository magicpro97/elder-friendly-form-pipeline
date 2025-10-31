#!/usr/bin/env python3
"""Test script for Elder-Friendly Form Pipeline"""

import json

import requests  # type: ignore

BASE_URL = "http://127.0.0.1:8000"


def test_list_forms():
    """Test GET /forms endpoint"""
    print("=" * 60)
    print("TEST 1: List Available Forms")
    print("=" * 60)

    response = requests.get(f"{BASE_URL}/forms")
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
    return response.status_code == 200


def test_complete_form_flow():
    """Test complete form submission flow"""
    print("\n" + "=" * 60)
    print("TEST 2: Complete Form Flow - Đơn Xin Việc")
    print("=" * 60)

    # Step 1: Start session
    print("\n--- Step 1: Start Session ---")
    response = requests.post(f"{BASE_URL}/session/start", json={"form": "don_xin_viec"})
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"Question: {data.get('ask')}")

    session_id = data["session_id"]
    print(f"Session ID: {session_id}")

    # Step 2: Answer questions
    answers = [
        ("Nguyễn Văn Bình", "Họ tên"),
        ("15/05/1960", "Ngày sinh"),
        ("123 Nguyễn Huệ, Quận 1, TP.HCM", "Địa chỉ"),
        ("0901234567", "Số điện thoại"),
        ("nvbinh@email.com", "Email"),
        ("Kỹ sư phần mềm", "Vị trí ứng tuyển"),
        ("10 năm kinh nghiệm lập trình Python, FastAPI", "Kinh nghiệm"),
    ]

    for idx, (answer, label) in enumerate(answers, 1):
        print(f"\n--- Step {idx + 1}: Answer - {label} ---")
        response = requests.post(f"{BASE_URL}/answer", json={"session_id": session_id, "text": answer})
        print(f"Status: {response.status_code}")
        data = response.json()

        if not data.get("ok"):
            print(f"Error: {data.get('message')}")
            if "confirm" in data:
                # Handle confirmation
                print(f"Confirmation needed: {data.get('confirm')}")
                confirm_response = requests.post(
                    f"{BASE_URL}/confirm", params={"session_id": session_id, "yes": "true"}
                )
                print(f"Confirmed: {confirm_response.json()}")
                data = confirm_response.json()

        if data.get("ask"):
            print(f"Next question: {data.get('ask')}")
        elif data.get("preview_ready"):
            print("✓ All questions answered! Preview ready.")
            break

    # Step 3: Get preview
    print("\n--- Step: Get Preview ---")
    response = requests.get(f"{BASE_URL}/preview", params={"session_id": session_id})
    print(f"Status: {response.status_code}")
    data = response.json()
    if data.get("ok"):
        print(f"Preview:\n{data.get('preview', 'No preview')}")
    else:
        print(f"Error: {data.get('message')}")

    # Step 4: Export PDF
    print("\n--- Step: Export PDF ---")
    response = requests.get(f"{BASE_URL}/export_pdf", params={"session_id": session_id})
    print(f"Status: {response.status_code}")

    if response.status_code == 200:
        filename = f"test_form_{session_id[:8]}.pdf"
        with open(filename, "wb") as f:
            f.write(response.content)
        print(f"✓ PDF exported successfully: {filename}")
        return True
    else:
        print(f"Error: {response.json()}")
        return False


def test_error_handling():
    """Test error handling"""
    print("\n" + "=" * 60)
    print("TEST 3: Error Handling")
    print("=" * 60)

    # Test invalid session
    print("\n--- Test: Invalid Session ID ---")
    response = requests.post(f"{BASE_URL}/answer", json={"session_id": "invalid-session-id", "text": "test"})
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    # Test missing form
    print("\n--- Test: Invalid Form ID ---")
    response = requests.post(f"{BASE_URL}/session/start", json={"form": "non_existent_form"})
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

    return True


def test_validation():
    """Test field validation"""
    print("\n" + "=" * 60)
    print("TEST 4: Field Validation")
    print("=" * 60)

    # Start new session
    response = requests.post(f"{BASE_URL}/session/start", json={"form": "don_xin_viec"})
    session_id = response.json()["session_id"]

    # Test invalid name (numbers)
    print("\n--- Test: Invalid Name (with numbers) ---")
    response = requests.post(f"{BASE_URL}/answer", json={"session_id": session_id, "text": "Nguyen123"})
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"OK: {data.get('ok')}")
    print(f"Message: {data.get('message', '')}")

    # Test valid name
    print("\n--- Test: Valid Name ---")
    response = requests.post(f"{BASE_URL}/answer", json={"session_id": session_id, "text": "Nguyễn Văn An"})
    print(f"Status: {response.status_code}")
    data = response.json()
    print(f"OK: {data.get('ok')}")
    print(f"Next field: {data.get('field', '')}")

    return True


def main():
    """Run all tests"""
    print("\n" + "🚀 " * 15)
    print("ELDER-FRIENDLY FORM PIPELINE - INTEGRATION TEST")
    print("🚀 " * 15)

    try:
        results = {
            "List Forms": test_list_forms(),
            "Complete Form Flow": test_complete_form_flow(),
            "Error Handling": test_error_handling(),
            "Field Validation": test_validation(),
        }

        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        for test_name, passed in results.items():
            status = "✓ PASSED" if passed else "✗ FAILED"
            print(f"{test_name}: {status}")

        all_passed = all(results.values())
        print("\n" + ("🎉 ALL TESTS PASSED!" if all_passed else "⚠️  SOME TESTS FAILED"))

    except requests.exceptions.ConnectionError:
        print("\n❌ ERROR: Cannot connect to server at http://127.0.0.1:8000")
        print("Please ensure the server is running with: uvicorn app:app --reload --port 8000")
    except Exception as e:
        print(f"\n❌ ERROR: {e}")


if __name__ == "__main__":
    main()
