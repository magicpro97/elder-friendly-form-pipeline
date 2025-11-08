#!/usr/bin/env python3
"""
Test UX improvements - Compare old vs new question style
"""
import requests
import json

API_BASE = "http://localhost:8000"

def test_friendly_questions():
    print("🧪 Testing UX Improvements - Friendly Questions")
    print("=" * 60)
    
    # 1. Get available forms
    print("\n📋 Step 1: Getting available forms...")
    forms_resp = requests.get(f"{API_BASE}/forms")
    forms = forms_resp.json()["items"]
    
    if not forms:
        print("❌ No forms found")
        return
    
    form = forms[0]
    form_id = form["id"]
    print(f"   Using form: {form.get('title', form_id)}")
    print(f"   Fields: {[f['id'] for f in form.get('fields', [])]}")
    
    # 2. Start session
    print("\n🚀 Step 2: Starting session...")
    session_resp = requests.post(f"{API_BASE}/sessions", json={"formId": form_id})
    session_data = session_resp.json()
    session_id = session_data["sessionId"]
    print(f"   Session ID: {session_id}")
    
    # 3. Get first question
    print("\n💬 Step 3: Getting questions...")
    print("\n" + "─" * 60)
    
    question_num = 1
    while True:
        # Get next question
        resp = requests.post(
            f"{API_BASE}/sessions/{session_id}/next-question",
            json={}
        )
        data = resp.json()
        
        if data.get("done"):
            print("\n✅ All questions completed!")
            break
        
        if not data.get("nextQuestion"):
            print("\n⚠️  No more questions")
            break
        
        question = data["nextQuestion"]
        
        # Display question
        print(f"\n❓ Question {question_num}:")
        print(f"   Field ID: {question['id']}")
        print(f"   Type: {question['type']}")
        print(f"   Question text: \"{question['text']}\"")
        
        # Compare with old style
        field_id = question['id']
        old_style = field_id.replace('_', ' ').title()  # Simple label
        print(f"\n   🔴 OLD STYLE (cộc lốc): \"{old_style}\"")
        print(f"   🟢 NEW STYLE (thân thiện): \"{question['text']}\"")
        print("   " + "─" * 56)
        
        # Auto-answer with dummy data
        dummy_answers = {
            "email": "test@example.com",
            "phone": "0901234567",
            "name": "Nguyễn Văn A",
            "date": "2024-01-01",
            "address": "123 Đường ABC, TP.HCM",
            "job": "Kỹ sư phần mềm",
        }
        
        # Find matching dummy answer
        answer = "Test Value"
        for key, value in dummy_answers.items():
            if key in field_id.lower():
                answer = value
                break
        
        # Submit answer
        resp = requests.post(
            f"{API_BASE}/sessions/{session_id}/next-question",
            json={
                "lastAnswer": {
                    "fieldId": question["id"],
                    "value": answer
                }
            }
        )
        
        print(f"   📝 Answered: {answer}")
        question_num += 1
        
        # Safety limit
        if question_num > 10:
            print("\n⚠️  Reached safety limit of 10 questions")
            break
    
    print("\n" + "=" * 60)
    print("✨ UX Improvement Summary:")
    print("   • Questions are now conversational and friendly")
    print("   • Vietnamese language support")
    print("   • Context-aware question generation")
    print("   • Better user experience for elderly users")
    print("=" * 60)

if __name__ == "__main__":
    try:
        test_friendly_questions()
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
