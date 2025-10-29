"""
Quick Verification: Check if Pinecone is configured correctly
"""
import os
from dotenv import load_dotenv

load_dotenv()

print("=" * 70)
print("  CONFIGURATION VERIFICATION")
print("=" * 70)
print()

# Check VECTOR_DB
vector_db = os.getenv('VECTOR_DB')
print(f"1. VECTOR_DB: {vector_db}")
if vector_db == 'pinecone':
    print("   [OK] Set to Pinecone (Cloud)")
elif vector_db == 'chromadb':
    print("   [WARNING] Still set to ChromaDB - should be 'pinecone'")
else:
    print("   [ERROR] Not set or invalid value")

print()

# Check Pinecone API Key
pinecone_key = os.getenv('PINECONE_API_KEY')
if pinecone_key and pinecone_key.startswith('pcsk_'):
    print(f"2. PINECONE_API_KEY: {pinecone_key[:20]}...")
    print("   [OK] Pinecone API key is configured")
else:
    print("2. PINECONE_API_KEY: Not set")
    print("   [ERROR] Pinecone API key missing")

print()

# Check Pinecone Index
index_name = os.getenv('PINECONE_INDEX_NAME')
print(f"3. PINECONE_INDEX_NAME: {index_name}")
if index_name:
    print("   [OK] Index name configured")
else:
    print("   [WARNING] Index name not set")

print()

# Check MongoDB
mongodb_uri = os.getenv('MONGODB_URI')
if mongodb_uri:
    if 'mongodb+srv://' in mongodb_uri:
        if 'YOUR_PASSWORD' in mongodb_uri or 'YOUR_CLUSTER' in mongodb_uri:
            print(f"4. MONGODB_URI: mongodb+srv://***PLACEHOLDER***")
            print("   [WARNING] Using placeholder - needs real credentials")
        else:
            print(f"4. MONGODB_URI: mongodb+srv://***CONFIGURED***")
            print("   [OK] MongoDB Atlas connection configured")
    elif 'localhost' in mongodb_uri:
        print(f"4. MONGODB_URI: mongodb://localhost:27017/")
        print("   [INFO] Using local MongoDB")
    else:
        print(f"4. MONGODB_URI: {mongodb_uri[:30]}...")
        print("   [INFO] Custom MongoDB connection")
else:
    print("4. MONGODB_URI: Not set")
    print("   [ERROR] MongoDB connection not configured")

print()
print("=" * 70)
print("  SUMMARY")
print("=" * 70)

issues = []
if vector_db != 'pinecone':
    issues.append("- VECTOR_DB should be 'pinecone'")
if not pinecone_key or not pinecone_key.startswith('pcsk_'):
    issues.append("- PINECONE_API_KEY not configured")
if not index_name:
    issues.append("- PINECONE_INDEX_NAME not set")
if not mongodb_uri:
    issues.append("- MONGODB_URI not configured")
elif 'YOUR_PASSWORD' in mongodb_uri or 'YOUR_CLUSTER' in mongodb_uri:
    issues.append("- MONGODB_URI needs real credentials (replace YOUR_PASSWORD and YOUR_CLUSTER)")

if not issues:
    print()
    print("  [OK] All configurations are correct!")
    print()
    print("  Next Step: Restart your Django server")
    print("  Run: python manage.py runserver")
    print()
else:
    print()
    print("  Issues Found:")
    for issue in issues:
        print(f"    {issue}")
    print()
    print("  Please update .env file and try again")
    print()

print("=" * 70)
