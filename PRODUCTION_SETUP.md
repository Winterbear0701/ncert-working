# 🚀 Production Setup - NCERT Learning Platform

## ✅ Current Architecture

### **Cloud Vector Database: Pinecone**
- **Purpose**: Stores PDF text chunks and embeddings for RAG (Retrieval Augmented Generation)
- **Index**: `ncert-learning-rag`
- **Dimensions**: 384 (sentence-transformers/all-MiniLM-L6-v2)
- **Region**: AWS us-east-1 (Serverless)
- **Status**: ✅ Connected and operational
- **Current Vectors**: 0 (ready for upload)

### **Cloud Database: MongoDB Atlas**
- **Purpose**: Stores all application data
- **Cluster**: cluster0.jxdvukx.mongodb.net
- **Database**: ncert_learning_db
- **Status**: ✅ Connected and operational
- **Collections**: Empty (ready for fresh data)

**Stores:**
- Users (students, teachers, superadmins)
- Quiz chapters, questions, variants
- Quiz attempts and scores
- Unit tests and evaluations
- Chat history, cache, memories
- Upload metadata

### **Local Database: SQLite (In-Memory)**
- **Purpose**: Django admin/auth sessions only
- **Mode**: In-memory (temporary)
- **Data**: Lost on server restart
- **Note**: Minimal usage, not for production data

---

## 🔐 Environment Variables

All configured in `.env`:

```bash
# Vector Database
VECTOR_DB=pinecone
PINECONE_API_KEY=pcsk_ZxjXy_...(configured)
PINECONE_INDEX_NAME=ncert-learning-rag

# MongoDB Atlas
MONGODB_URI=mongodb+srv://sajithjaganathan7_db_user:***@cluster0.jxdvukx.mongodb.net/
MONGODB_DB_NAME=ncert_learning_db

# AI APIs
OPENAI_API_KEY=sk-proj-...(configured)
GEMINI_API_KEY=AIzaSy...(configured)
```

---

## 📦 Key Files

### **Active Production Files**
- `ncert_project/pinecone_utils.py` - Pinecone vector database manager
- `ncert_project/vector_db_utils.py` - Unified vector DB interface (auto-switches)
- `ncert_project/mongodb_utils.py` - MongoDB Atlas manager
- `test_pinecone.py` - Pinecone connection test
- `reset_database.py` - Clean reset script (wipes all data)
- `requirements.txt` - Python dependencies

### **Legacy Files (Fallback Only)**
- `ncert_project/chromadb_utils.py` - Old ChromaDB implementation (not used)
- `ncert_project/settings.py` - Has ChromaDB config (ignored when VECTOR_DB=pinecone)

---

## 🧪 Testing Setup

Run test to verify Pinecone connection:
```bash
python test_pinecone.py
```

**Expected Output:**
```
✅ Pinecone connection: Working
✅ Index access: Working
✅ Query operations: Working
✅ Add operations: Working
```

---

## 🔄 Fresh Start Process

If you need to wipe all data and start fresh:

```bash
python reset_database.py
```

**Prompts:**
1. Type `DELETE ALL` to confirm
2. Enter superadmin details:
   - Full Name (e.g., Sajith J)
   - Email (e.g., sajithjaganathan7@gmail.com)
   - Username (e.g., admin)
   - Password (e.g., Winter_07)

**What Gets Deleted:**
- All MongoDB Atlas collections (users, quizzes, scores, chat, uploads)
- All Pinecone vectors (embeddings)
- All uploaded PDFs and images
- SQLite database (if exists)

**What Gets Created:**
- Fresh MongoDB collections
- Empty Pinecone index (ready for uploads)
- New superadmin user

---

## 📚 Upload Flow (Production)

1. **Student/Teacher uploads PDF** → Saved to `media/uploads/`
2. **PDF Processing** → Extracted text chunks
3. **Embedding Generation** → sentence-transformers (all-MiniLM-L6-v2)
4. **Vector Storage** → Pinecone (ncert-learning-rag index)
5. **Metadata Storage** → MongoDB Atlas (uploads collection)

**Configuration Check:**
```python
# In Django shell or views.py
from ncert_project.vector_db_utils import get_vector_db_manager

manager = get_vector_db_manager()
print(type(manager).__name__)  # Should print: PineconeDBManager
```

---

## 🚨 Troubleshooting

### Pinecone Connection Issues
```bash
python test_pinecone.py
```
If fails, check:
- `PINECONE_API_KEY` in `.env`
- `VECTOR_DB=pinecone` in `.env`
- Internet connection

### MongoDB Connection Issues
```bash
python manage.py shell
```
```python
from ncert_project.mongodb_utils import get_mongodb_manager
manager = get_mongodb_manager()
print(manager.db.name)  # Should print: ncert_learning_db
```

If fails, check:
- `MONGODB_URI` in `.env` (username/password correct)
- MongoDB Atlas IP whitelist (0.0.0.0/0 for development)

### Wrong Vector DB Being Used
```bash
grep "Using.*for vector storage" logs/*.log
```
Should show: "Using Pinecone for vector storage"

If shows ChromaDB:
1. Check `.env` has `VECTOR_DB=pinecone`
2. Restart Django server: `python manage.py runserver`

---

## 📊 Current Status (Fresh Setup)

| Component | Status | Data |
|-----------|--------|------|
| Pinecone (Vectors) | ✅ Connected | 0 vectors |
| MongoDB Atlas (App Data) | ✅ Connected | 0 collections |
| Django Migrations | ✅ Applied | Up to date |
| Superadmin | ✅ Created | sajithjaganathan7@gmail.com |
| Media Files | ✅ Empty | Ready for uploads |

---

## ✅ Next Steps

1. **Upload NCERT PDFs** through the admin panel
2. **Verify vectors** are going to Pinecone (not ChromaDB)
3. **Create quizzes** from uploaded content
4. **Test RAG chatbot** with uploaded chapters

---

## 🔧 Dependencies

```bash
pinecone>=7.0.0          # Cloud vector database
pymongo>=4.6.0           # MongoDB Atlas driver
sentence-transformers     # Embedding model
chromadb>=0.4.22         # Legacy (fallback only)
```

---

## 📝 Notes

- **ChromaDB** code is kept for backward compatibility but NOT used when `VECTOR_DB=pinecone`
- **Migration scripts** (migrate_to_pinecone.py, setup_pinecone.py) removed - use fresh upload instead
- **SQLite** is only for Django admin sessions (temporary)
- **Pinecone** handles up to 100K vectors on free tier
- **MongoDB Atlas** has 512MB free tier

---

**Last Updated**: Fresh setup completed
**Status**: Production ready ✅
