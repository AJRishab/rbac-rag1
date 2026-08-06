"""
Sentry RAG - Backend API Tests
Tests all critical endpoints including auth, admin, and RBAC-filtered chat.
"""
import os
import requests
import sys
import time
from datetime import datetime

BASE_URL = "http://localhost:7860/api"

# Supabase connection for obtaining access tokens (login / signup).
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY", "")

# Test accounts (override via env).
TEST_ADMIN_EMAIL = os.environ.get("TEST_ADMIN_EMAIL", "admin@sentry.local")
TEST_ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "Admin@2026")
TEST_EMPLOYEE_EMAIL = os.environ.get("TEST_EMPLOYEE_EMAIL", "employee@test.co")
TEST_MANAGER_EMAIL = os.environ.get("TEST_MANAGER_EMAIL", "manager@test.co")
TEST_HR_EMAIL = os.environ.get("TEST_HR_EMAIL", "hr@test.co")
TEST_PASSWORD = os.environ.get("TEST_PASSWORD", "Test@1234")

class SentryRAGTester:
    def __init__(self):
        self.base_url = BASE_URL
        self.tokens = {}
        self.tests_run = 0
        self.tests_passed = 0
        self.test_results = []

    def log_test(self, name, passed, details=""):
        """Log test result"""
        self.tests_run += 1
        if passed:
            self.tests_passed += 1
            print(f"✅ PASS: {name}")
        else:
            print(f"❌ FAIL: {name}")
        if details:
            print(f"   {details}")
        self.test_results.append({
            "name": name,
            "passed": passed,
            "details": details
        })

    def test_health(self):
        """Test health endpoint"""
        try:
            response = requests.get(f"{self.base_url}/health", timeout=10)
            passed = response.status_code == 200
            self.log_test("Health Check", passed, f"Status: {response.status_code}")
            return passed
        except Exception as e:
            self.log_test("Health Check", False, f"Error: {str(e)}")
            return False

    def test_login(self, email, password, expected_status=200):
        """Sign in via Supabase Auth and return the access token.

        Login is no longer a backend endpoint — supabase-js (or this REST call)
        exchanges email+password for a Supabase JWT, which the backend verifies.
        """
        try:
            response = requests.post(
                f"{SUPABASE_URL}/auth/v1/token",
                params={"grant_type": "password"},
                headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
                json={"email": email, "password": password},
                timeout=10
            )
            passed = response.status_code == expected_status

            if passed and response.status_code == 200:
                data = response.json()
                token = data.get("access_token")
                if token:
                    self.tokens[email] = token
                    self.log_test(f"Login as {email}", True, "Supabase access token received")
                else:
                    self.log_test(f"Login as {email}", False, "No access_token in response")
                    passed = False
            else:
                self.log_test(f"Login as {email}", passed, f"Status: {response.status_code}, Body: {response.text[:200]}")

            return passed
        except Exception as e:
            self.log_test(f"Login as {email}", False, f"Error: {str(e)}")
            return False

    def test_register(self, email, password):
        """Sign up a new user via Supabase Auth."""
        try:
            response = requests.post(
                f"{SUPABASE_URL}/auth/v1/signup",
                headers={"apikey": SUPABASE_ANON_KEY, "Content-Type": "application/json"},
                json={"email": email, "password": password},
                timeout=10
            )
            passed = response.status_code in [200, 201]

            if passed:
                data = response.json()
                self.log_test(f"Register {email}", True, f"Status: {data.get('status', 'N/A')}")
            else:
                self.log_test(f"Register {email}", False, f"Status: {response.status_code}, Body: {response.text[:200]}")

            return passed
        except Exception as e:
            self.log_test(f"Register {email}", False, f"Error: {str(e)}")
            return False

    def test_admin_get_users(self, admin_email):
        """Test admin get users endpoint"""
        if admin_email not in self.tokens:
            self.log_test("Admin Get Users", False, "Admin not logged in")
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/admin/users",
                headers={"Authorization": f"Bearer {self.tokens[admin_email]}"},
                timeout=10
            )
            passed = response.status_code == 200
            
            if passed:
                data = response.json()
                # API returns list directly
                if isinstance(data, list):
                    pending_count = len([u for u in data if u.get("status") == "pending"])
                    approved_count = len([u for u in data if u.get("status") == "approved"])
                    self.log_test("Admin Get Users", True, f"Total: {len(data)}, Pending: {pending_count}, Approved: {approved_count}")
                else:
                    self.log_test("Admin Get Users", False, f"Unexpected response format: {type(data)}")
                    passed = False
            else:
                self.log_test("Admin Get Users", False, f"Status: {response.status_code}")
            
            return passed
        except Exception as e:
            self.log_test("Admin Get Users", False, f"Error: {str(e)}")
            return False

    def test_admin_get_documents(self, admin_email):
        """Test admin get documents endpoint"""
        if admin_email not in self.tokens:
            self.log_test("Admin Get Documents", False, "Admin not logged in")
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/admin/documents",
                headers={"Authorization": f"Bearer {self.tokens[admin_email]}"},
                timeout=10
            )
            passed = response.status_code == 200
            
            if passed:
                data = response.json()
                # API returns list directly
                if isinstance(data, list):
                    doc_count = len(data)
                    self.log_test("Admin Get Documents", True, f"Documents: {doc_count}")
                    if doc_count > 0:
                        print(f"   Sample doc: {data[0].get('title', 'N/A')}, roles: {data[0].get('allowed_roles', [])}")
                else:
                    self.log_test("Admin Get Documents", False, f"Unexpected response format: {type(data)}")
                    passed = False
            else:
                self.log_test("Admin Get Documents", False, f"Status: {response.status_code}")
            
            return passed
        except Exception as e:
            self.log_test("Admin Get Documents", False, f"Error: {str(e)}")
            return False

    def test_chat_ask(self, email, question, expected_min_retrieved=0):
        """Test chat ask endpoint with RBAC"""
        if email not in self.tokens:
            self.log_test(f"Chat Ask ({email})", False, f"{email} not logged in")
            return {"passed": False}
        
        try:
            # Add delay to avoid NIM rate limits
            time.sleep(2)
            
            response = requests.post(
                f"{self.base_url}/chat/ask",
                headers={"Authorization": f"Bearer {self.tokens[email]}"},
                json={"question": question, "conversation_id": None},
                timeout=30  # Longer timeout for LLM
            )
            passed = response.status_code == 200
            
            if passed:
                data = response.json()
                # Response structure: {conversation_id, user_message, assistant_message}
                asst_msg = data.get("assistant_message", {})
                retrieved = asst_msg.get("retrieved_count", 0)
                blocked = asst_msg.get("blocked_count", 0)
                answer = asst_msg.get("content", "")
                citations = asst_msg.get("citations", [])
                
                answer_preview = answer[:100] if answer else "No answer"
                
                self.log_test(
                    f"Chat Ask ({email})",
                    True,
                    f"Retrieved: {retrieved}, Blocked: {blocked}, Citations: {len(citations)}, Answer: {answer_preview}..."
                )
                
                # Store for RBAC verification
                return {
                    "passed": True,
                    "retrieved": retrieved,
                    "blocked": blocked,
                    "answer": answer,
                    "citations": citations
                }
            else:
                self.log_test(f"Chat Ask ({email})", False, f"Status: {response.status_code}, Body: {response.text[:200]}")
                return {"passed": False}
            
        except Exception as e:
            self.log_test(f"Chat Ask ({email})", False, f"Error: {str(e)}")
            return {"passed": False}

    def test_chat_history(self, email):
        """Test chat history endpoint"""
        if email not in self.tokens:
            self.log_test(f"Chat History ({email})", False, f"{email} not logged in")
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/chat/conversations",
                headers={"Authorization": f"Bearer {self.tokens[email]}"},
                timeout=10
            )
            passed = response.status_code == 200
            
            if passed:
                data = response.json()
                # API returns list directly
                if isinstance(data, list):
                    conv_count = len(data)
                    self.log_test(f"Chat History ({email})", True, f"Conversations: {conv_count}")
                else:
                    self.log_test(f"Chat History ({email})", False, f"Unexpected response format: {type(data)}")
                    passed = False
            else:
                self.log_test(f"Chat History ({email})", False, f"Status: {response.status_code}")
            
            return passed
        except Exception as e:
            self.log_test(f"Chat History ({email})", False, f"Error: {str(e)}")
            return False

    def test_non_admin_cannot_access_admin(self, email):
        """Test that non-admin cannot access admin endpoints"""
        if email not in self.tokens:
            self.log_test(f"Non-Admin Access Block ({email})", False, f"{email} not logged in")
            return False
        
        try:
            response = requests.get(
                f"{self.base_url}/admin/users",
                headers={"Authorization": f"Bearer {self.tokens[email]}"},
                timeout=10
            )
            # Should get 403 or 401
            passed = response.status_code in [401, 403]
            
            if passed:
                self.log_test(f"Non-Admin Access Block ({email})", True, f"Correctly blocked with {response.status_code}")
            else:
                self.log_test(f"Non-Admin Access Block ({email})", False, f"Expected 401/403, got {response.status_code}")
            
            return passed
        except Exception as e:
            self.log_test(f"Non-Admin Access Block ({email})", False, f"Error: {str(e)}")
            return False

    def print_summary(self):
        """Print test summary"""
        print("\n" + "="*60)
        print(f"📊 TEST SUMMARY")
        print("="*60)
        print(f"Total Tests: {self.tests_run}")
        print(f"Passed: {self.tests_passed}")
        print(f"Failed: {self.tests_run - self.tests_passed}")
        print(f"Success Rate: {(self.tests_passed/self.tests_run*100):.1f}%")
        print("="*60)


def main():
    print("🚀 Starting Sentry RAG Backend Tests")
    print(f"Base URL: {BASE_URL}\n")
    
    tester = SentryRAGTester()
    
    # Test 1: Health check
    print("\n--- BASIC CONNECTIVITY ---")
    if not tester.test_health():
        print("❌ Health check failed, stopping tests")
        return 1
    
    # Test 2: Login with existing users
    print("\n--- AUTHENTICATION ---")
    tester.test_login(TEST_ADMIN_EMAIL, TEST_ADMIN_PASSWORD)
    tester.test_login(TEST_EMPLOYEE_EMAIL, TEST_PASSWORD)
    tester.test_login(TEST_MANAGER_EMAIL, TEST_PASSWORD)
    tester.test_login(TEST_HR_EMAIL, TEST_PASSWORD)
    
    # Test 3: Register new pending user
    print("\n--- REGISTRATION ---")
    test_email = f"pending{int(time.time())}@test.co"
    tester.test_register(test_email, TEST_PASSWORD)
    
    # Test 4: Admin endpoints
    print("\n--- ADMIN ENDPOINTS ---")
    tester.test_admin_get_users(TEST_ADMIN_EMAIL)
    tester.test_admin_get_documents(TEST_ADMIN_EMAIL)
    
    # Test 5: Non-admin cannot access admin
    print("\n--- AUTHORIZATION ---")
    tester.test_non_admin_cannot_access_admin(TEST_EMPLOYEE_EMAIL)
    
    # Test 6: Chat history
    print("\n--- CHAT HISTORY ---")
    tester.test_chat_history(TEST_EMPLOYEE_EMAIL)
    tester.test_chat_history(TEST_HR_EMAIL)
    
    # Test 7: RBAC differentiation - THE CORE TEST
    print("\n--- RBAC DIFFERENTIATION (CORE TEST) ---")
    question = "What is our compensation policy for software engineers?"
    
    print("\n🔍 Testing RBAC: Same question, different roles...")
    employee_result = tester.test_chat_ask(TEST_EMPLOYEE_EMAIL, question)
    time.sleep(2)  # Rate limit protection
    hr_result = tester.test_chat_ask(TEST_HR_EMAIL, question)
    time.sleep(2)
    admin_result = tester.test_chat_ask(TEST_ADMIN_EMAIL, question)
    
    # Verify RBAC differentiation
    print("\n--- RBAC VERIFICATION ---")
    if employee_result.get("passed") and hr_result.get("passed"):
        # Employee should have fewer retrieved, more blocked
        employee_retrieved = employee_result.get("retrieved", 0)
        employee_blocked = employee_result.get("blocked", 0)
        hr_retrieved = hr_result.get("retrieved", 0)
        hr_blocked = hr_result.get("blocked", 0)
        
        rbac_working = (
            hr_retrieved > employee_retrieved and
            hr_blocked < employee_blocked
        )
        
        if rbac_working:
            tester.log_test(
                "RBAC Differentiation",
                True,
                f"Employee: {employee_retrieved} retrieved, {employee_blocked} blocked | HR: {hr_retrieved} retrieved, {hr_blocked} blocked"
            )
        else:
            tester.log_test(
                "RBAC Differentiation",
                False,
                f"RBAC not working as expected. Employee: {employee_retrieved}/{employee_blocked}, HR: {hr_retrieved}/{hr_blocked}"
            )
    else:
        tester.log_test("RBAC Differentiation", False, "Could not complete RBAC test due to chat failures")
    
    # Print summary
    tester.print_summary()
    
    return 0 if tester.tests_passed == tester.tests_run else 1


if __name__ == "__main__":
    sys.exit(main())
