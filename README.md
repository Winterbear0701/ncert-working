# 🎓 NCERT Learning Platform

An intelligent, AI-powered learning platform for NCERT curriculum with advanced features including adaptive quizzes, intelligent chatbot, and cloud-native architecture.

## ✨ Features

### 🎯 Student Features
- **Adaptive Learning**: Progressive chapter unlocking based on performance (70% pass threshold)
- **Interactive Quizzes**: AI-generated MCQs with detailed explanations
- **Smart Chatbot**: RAG-powered doubt resolution using course content
- **Progress Tracking**: Real-time monitoring of learning progress and scores
- **Chapter Management**: Structured learning path with locked/unlocked chapters

### 👨‍💼 Admin Features
- **PDF Upload**: Easy upload and processing of NCERT textbooks
- **Quiz Generation**: Automated quiz creation using AI
- **Content Management**: Upload, view, and delete educational content
- **Analytics**: Monitor student progress and performance

### 🏗️ Technical Features
- **Cloud-Native Architecture**: MongoDB Atlas + Pinecone for scalability
- **Hybrid Vector Storage**: ChromaDB (dev) / Pinecone (production)
- **AI Integration**: OpenAI GPT-4 and Google Gemini
- **Modern Stack**: Django 4.2.11 with async capabilities

---

## 🚀 Quick Start

### Prerequisites
- Python 3.12.3
- MongoDB Atlas account
- Pinecone account (for production)
- OpenAI/Google AI API keys

### 1. Setup Environment

```bash
# Clone repository (or navigate to project)
cd ncert-working

# Create virtual environment
python -m venv ncert
source ncert/bin/activate  # Windows: ncert\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Create/edit `.env` file:

```bash
# Django
SECRET_KEY=your-django-secret-key
DEBUG=True

# MongoDB Atlas (Required)
MONGODB_URI=mongodb+srv://username:password@cluster.mongodb.net/
MONGODB_DB_NAME=ncert_db

# AI APIs (Required)
OPENAI_API_KEY=sk-...
GOOGLE_API_KEY=AI...

# Vector Database (Choose one)
VECTOR_DB=chromadb              # For local development
# VECTOR_DB=pinecone            # For production

# Pinecone (Optional - for production only)
PINECONE_API_KEY=pcsk_...       # Get from https://app.pinecone.io/
PINECONE_ENVIRONMENT=us-east-1-aws
PINECONE_INDEX_NAME=ncert-learning-rag
```

### 3. Initialize Database

```bash
# Run Django migrations (for admin sessions)
python manage.py migrate

# Create superuser
python manage.py createsuperuser
```

### 4. Start Server

```bash
python manage.py runserver
```

Visit: http://localhost:8000

---

## 📦 Production Setup (Pinecone Migration)

For production deployment with cloud vector storage:

### Quick Method (Recommended)
```bash
# 1. Get Pinecone API key from https://app.pinecone.io/
# 2. Add to .env file
# 3. Run setup wizard
python setup_pinecone.py
```

### Manual Method
```bash
# Test connection
python test_pinecone.py

# Migrate data from ChromaDB
python migrate_to_pinecone.py

# Update .env: VECTOR_DB=pinecone
# Restart server
```

**Documentation:**
- 📖 Quick Start: [`QUICKSTART_PINECONE.md`](QUICKSTART_PINECONE.md)
- 📚 Complete Guide: [`PINECONE_SETUP.md`](PINECONE_SETUP.md)
- 📊 Summary: [`PINECONE_SUMMARY.md`](PINECONE_SUMMARY.md)

---

## 🏗️ Architecture

### System Overview
```
Django Application
    ├── MongoDB Atlas (User data, quizzes, progress)
    ├── Vector DB (Document embeddings)
    │   ├── ChromaDB (Local development)
    │   └── Pinecone (Production)
    └── AI Models (OpenAI GPT-4, Google Gemini)
```

**Full Architecture:** [`ARCHITECTURE.md`](ARCHITECTURE.md)

### Key Components

| Component | Technology | Purpose |
|-----------|-----------|---------|
| Web Framework | Django 4.2.11 | Backend & API |
| Database | MongoDB Atlas | User & quiz data |
| Vector DB | ChromaDB/Pinecone | Document embeddings |
| AI Models | GPT-4, Gemini | Quiz & chat generation |
| Embeddings | sentence-transformers | Text vectorization |

---

## 📁 Project Structure

```
ncert-working/
├── accounts/                # User authentication & management
├── students/               # Student features
│   ├── views.py           # Chatbot, dashboard
│   ├── quiz_views.py      # Quiz system with unlocking logic
│   └── management/        # Management commands
├── superadmin/            # Admin features
│   ├── views.py          # Upload, delete, quiz generation
│   └── urls.py           # Admin routes
├── ncert_project/         # Project settings
│   ├── settings.py       # Django configuration
│   ├── chromadb_utils.py # ChromaDB manager
│   ├── pinecone_utils.py # Pinecone manager
│   └── vector_db_utils.py # Unified interface
├── templates/             # HTML templates
├── media/                # Uploaded PDFs
├── chromadb_data/        # ChromaDB storage (local)
│
├── migrate_to_pinecone.py    # Pinecone migration tool
├── test_pinecone.py          # Pinecone test script
├── setup_pinecone.py         # One-click setup wizard
├── reset_database.py         # Database reset utility
│
├── requirements.txt          # Python dependencies
├── .env                      # Environment configuration
├── manage.py                 # Django management
│
└── Documentation/
    ├── README.md                 # This file
    ├── QUICKSTART_PINECONE.md    # 5-minute Pinecone setup
    ├── PINECONE_SETUP.md         # Complete Pinecone guide
    ├── PINECONE_SUMMARY.md       # Migration summary
    ├── ARCHITECTURE.md           # System architecture
    ├── MONGODB_SETUP.md          # MongoDB configuration
    └── DATA_STORAGE_GUIDE.md     # Data management
```

---

## 🛠️ Technologies Used

### Core Stack
- **Django 4.2.11**: Web framework
- **Python 3.12.3**: Programming language
- **MongoDB Atlas**: Cloud database (99% of data)
- **SQLite**: Minimal admin session storage

### Vector Databases
- **ChromaDB 0.4.22**: Local development vector storage
- **Pinecone 6.0.0**: Production cloud vector storage

### AI & ML
- **OpenAI GPT-4**: Quiz generation, chatbot responses
- **Google Gemini AI**: Alternative AI model
- **sentence-transformers**: Text embeddings (all-MiniLM-L6-v2)
- **LangChain**: AI orchestration

### Document Processing
- **pdfplumber**: PDF text extraction
- **PyPDF2**: PDF manipulation
- **pytesseract**: OCR for images

### Deployment
- **gunicorn**: Production WSGI server
- **whitenoise**: Static file serving
- **django-cors-headers**: CORS support

---

## 📚 Key Features Explained

### 1. Progressive Chapter Unlocking

**How it works:**
- First chapter of each subject is always unlocked
- Complete chapter quiz with ≥70% to unlock next chapter
- Progress tracked per student per subject

**Code:** `students/quiz_views.py` → `quiz_dashboard()`

### 2. AI-Powered Chatbot

**How it works:**
- Student asks question → Vector DB finds relevant content → AI generates answer
- Uses RAG (Retrieval Augmented Generation) for accuracy
- Context-aware responses based on curriculum

**Code:** `students/views.py` → `process_chat_question()`

### 3. Smart Quiz Generation

**How it works:**
- Admin uploads PDF → Text extracted → Embeddings generated → Stored in vector DB
- Generate quiz → Retrieve chapter content → AI creates questions
- Questions stored in MongoDB for reuse

**Code:** `superadmin/views.py` → `generate_quiz()`

### 4. Unified Vector DB Interface

**How it works:**
- Single API works with both ChromaDB and Pinecone
- Switch databases via environment variable
- Zero code changes needed

**Code:** `ncert_project/vector_db_utils.py`

---

## 🔧 Management Commands

### Reset Chapter Locks
```bash
python manage.py reset_chapter_locks [--class CLASS] [--subject SUBJECT]
```

### Database Reset
```bash
# Reset everything (MongoDB + Vector DB)
python reset_database.py

# Interactive mode with confirmations
```

### Test Pinecone
```bash
# Test Pinecone connection and functionality
python test_pinecone.py
```

---

## 🧪 Testing

### Manual Testing

1. **Student Flow:**
   - Register → Login → View dashboard
   - Start quiz → Answer questions → Submit
   - Check if next chapter unlocks (if score ≥ 70%)
   - Test chatbot with questions

2. **Admin Flow:**
   - Login as superadmin → Upload PDF
   - Generate quiz → Verify questions
   - Test delete functionality

3. **Vector DB:**
   - Test ChromaDB: `VECTOR_DB=chromadb`
   - Test Pinecone: `VECTOR_DB=pinecone`
   - Verify chatbot works with both

### Automated Testing
```bash
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test students
python manage.py test superadmin
```

---

## 📊 Monitoring

### Check System Health

```bash
# MongoDB connection
python test_mongodb.py

# Vector DB status
python test_pinecone.py  # For Pinecone
ls chromadb_data/        # For ChromaDB

# Server logs
python manage.py runserver  # Check for startup messages
```

### Key Metrics

| Metric | Expected Value |
|--------|---------------|
| Page load time | < 2 seconds |
| Chatbot response | < 3 seconds |
| Quiz generation | < 30 seconds |
| MongoDB queries | < 100ms |
| Vector searches | < 500ms |

---

## 🐛 Troubleshooting

### Common Issues

**1. MongoDB Connection Failed**
```bash
# Check connection string in .env
# Verify IP whitelist in MongoDB Atlas
# Test connection: python test_mongodb.py
```

**2. Vector DB Not Working**
```bash
# For ChromaDB: Check chromadb_data/ exists
# For Pinecone: Run python test_pinecone.py
# Verify VECTOR_DB setting in .env
```

**3. Quiz Not Generating**
```bash
# Check OpenAI API key is valid
# Verify vector DB has content: python test_pinecone.py
# Check server logs for errors
```

**4. Chatbot Not Responding**
```bash
# Verify AI API keys in .env
# Check vector DB has embeddings
# Test query: python test_pinecone.py
```

---

## 📈 Scaling Guide

### Development (< 100 users)
```
✅ Current setup
- MongoDB Atlas: Free tier (512MB)
- Pinecone: Free tier (100K vectors)
- Single server: 1GB RAM
```

### Production (100-1000 users)
```
📈 Upgrade needed
- MongoDB Atlas: Shared cluster ($10/mo)
- Pinecone: Still free
- Server: 2GB RAM, load balancer
```

### Enterprise (10K+ users)
```
🚀 Full scale
- MongoDB Atlas: Dedicated cluster
- Pinecone: Standard/Enterprise plan
- Kubernetes: Auto-scaling
- CDN: Global distribution
```

---

## 🤝 Contributing

### Development Workflow

1. **Setup Dev Environment:**
   ```bash
   git pull origin main
   source ncert/bin/activate
   pip install -r requirements.txt
   ```

2. **Make Changes:**
   - Follow Django best practices
   - Update tests if needed
   - Document new features

3. **Test Changes:**
   ```bash
   python manage.py test
   python test_pinecone.py
   ```

4. **Commit:**
   ```bash
   git add .
   git commit -m "feat: description of changes"
   git push origin feature-branch
   ```

---

## 📄 License

This project is proprietary software. All rights reserved.

---

## 📞 Support

### Documentation
- 📖 Quick Start: `QUICKSTART_PINECONE.md`
- 📚 Full Guides: `PINECONE_SETUP.md`, `MONGODB_SETUP.md`
- 🏗️ Architecture: `ARCHITECTURE.md`

### External Resources
- MongoDB Atlas Docs: https://docs.atlas.mongodb.com/
- Pinecone Docs: https://docs.pinecone.io/
- Django Docs: https://docs.djangoproject.com/

---

## 🎯 Roadmap

### ✅ Completed
- [x] User authentication system
- [x] PDF upload & processing
- [x] AI quiz generation
- [x] Smart chatbot with RAG
- [x] Progressive chapter unlocking
- [x] MongoDB Atlas migration
- [x] Pinecone integration
- [x] Unified vector DB interface

### 🚧 In Progress
- [ ] Performance optimization
- [ ] Advanced analytics dashboard
- [ ] Mobile app development

### 📋 Planned
- [ ] Multi-language support
- [ ] Video content integration
- [ ] Peer-to-peer learning
- [ ] Gamification features
- [ ] Parent dashboard

---

## 🌟 Highlights

- **🚀 Production-Ready**: Cloud-native with MongoDB Atlas + Pinecone
- **🤖 AI-Powered**: GPT-4 for intelligent content generation
- **📈 Scalable**: Handles 100 users (free) to 100K+ users (paid)
- **🔧 Flexible**: Switch vector DBs with one environment variable
- **📚 Well-Documented**: Comprehensive guides for every feature
- **🧪 Tested**: Manual and automated testing coverage

---

**Last Updated:** Complete Pinecone migration infrastructure
**Version:** 2.0.0 (Cloud-Native)
**Status:** ✅ Production Ready

---

## 🎓 Happy Learning! 🚀

For questions or support, refer to the documentation files or check server logs for detailed error messages.
