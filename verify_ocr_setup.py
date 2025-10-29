"""
Quick Test: Verify OCR and Cross-Chapter Search Configuration
"""
import os
import sys
from pathlib import Path

# Add project to path
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# Django setup
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'ncert_project.settings')
import django
django.setup()

print("=" * 70)
print("  OCR + CROSS-CHAPTER SEARCH - VERIFICATION")
print("=" * 70)
print()

# Test 1: Check imports
print("1. Checking dependencies...")
try:
    import pytesseract
    print("   [OK] pytesseract installed")
except ImportError:
    print("   [ERROR] pytesseract not installed")

try:
    from pdf2image import convert_from_path
    print("   [OK] pdf2image installed")
except ImportError:
    print("   [ERROR] pdf2image not installed - run: pip install pdf2image")

try:
    from PIL import Image
    print("   [OK] Pillow (PIL) installed")
except ImportError:
    print("   [ERROR] Pillow not installed")

print()

# Test 2: Check Tesseract executable
print("2. Checking Tesseract OCR...")
try:
    version = pytesseract.get_tesseract_version()
    print(f"   [OK] Tesseract version: {version}")
except Exception as e:
    print(f"   [ERROR] Tesseract not found: {e}")
    print("   Install from: https://github.com/UB-Mannheim/tesseract/wiki")

print()

# Test 3: Check enhanced functions exist
print("3. Checking enhanced functions...")
try:
    from superadmin.tasks import extract_text_from_page_image_ocr
    print("   [OK] extract_text_from_page_image_ocr() function exists")
except ImportError as e:
    print(f"   [ERROR] Function not found: {e}")

try:
    from ncert_project.vector_db_utils import get_vector_db_manager
    vector_manager = get_vector_db_manager()
    print(f"   [OK] Vector DB manager: {type(vector_manager).__name__}")
except Exception as e:
    print(f"   [ERROR] Vector DB manager issue: {e}")

print()

# Test 4: Check Pinecone configuration
print("4. Checking Pinecone configuration...")
from dotenv import load_dotenv
load_dotenv()

vector_db = os.getenv('VECTOR_DB')
pinecone_key = os.getenv('PINECONE_API_KEY')

if vector_db == 'pinecone':
    print(f"   [OK] VECTOR_DB={vector_db}")
else:
    print(f"   [WARNING] VECTOR_DB={vector_db} (should be 'pinecone')")

if pinecone_key and pinecone_key.startswith('pcsk_'):
    print(f"   [OK] PINECONE_API_KEY configured")
else:
    print(f"   [ERROR] PINECONE_API_KEY not configured")

print()

# Test 5: Summary
print("=" * 70)
print("  SUMMARY")
print("=" * 70)
print()

issues = []
try:
    import pytesseract
    from pdf2image import convert_from_path
    from PIL import Image
    pytesseract.get_tesseract_version()
    from superadmin.tasks import extract_text_from_page_image_ocr
except Exception as e:
    issues.append(f"Dependency issue: {e}")

if vector_db != 'pinecone':
    issues.append("VECTOR_DB should be 'pinecone'")

if not pinecone_key or not pinecone_key.startswith('pcsk_'):
    issues.append("PINECONE_API_KEY not configured")

if not issues:
    print("  [OK] All checks passed!")
    print()
    print("  Ready to test:")
    print("  1. Restart Django server")
    print("  2. Upload PDF with diagrams (e.g., Rivers in India)")
    print("  3. Watch for OCR extraction logs")
    print("  4. Ask 'What is dune?' to test cross-chapter search")
    print()
else:
    print("  Issues found:")
    for issue in issues:
        print(f"    - {issue}")
    print()
    print("  Fix these issues before testing")
    print()

print("=" * 70)
print()
print("  Test Commands:")
print("  - Test Tesseract: tesseract --version")
print("  - Test pdf2image: python -c \"from pdf2image import convert_from_path; print('OK')\"")
print("  - Restart server: python manage.py runserver")
print()
print("=" * 70)
