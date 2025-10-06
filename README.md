# NCERT Learning Platform - AI-Powered Tutoring System

A production-ready Django application that provides AI-powered tutoring for NCERT curriculum (Standards 5-10) using RAG (Retrieval Augmented Generation) with OpenAI and Google Gemini.

## 🌟 Features

- **AI Chatbot**: Intelligent tutoring using OpenAI GPT-4 and Google Gemini with RAG
- **PDF Processing**: Automated PDF chunking and embedding storage in ChromaDB
- **Superadmin Dashboard**: Upload and manage NCERT textbooks with metadata mapping
- **Student Dashboard**: Interactive chat interface with typing indicators and animations
- **Async Processing**: Celery-based background tasks for PDF processing
- **Production Ready**: Comprehensive logging, error handling, and security settings
- **Modern UI**: Beautiful Tailwind CSS interface with smooth animations

## 📋 Prerequisites

- Python 3.10+
- Redis Server (for Celery)
- Git

## 🚀 Installation

### 1. Clone the Repository

```bash
git clone https://github.com/Winterbear0701/ncert-working.git
cd new-intel-ncert
```

### 2. Create and Activate Virtual Environment

The project already has a virtual environment in `ncert/`. Activate it:

```powershell
# Windows PowerShell
.\ncert\Scripts\Activate.ps1
```

### 3. Install Dependencies

```powershell
pip install -r requirements.txt
```

### 4. Configure Environment Variables

Create a `.env` file in the project root (already exists, verify it has):

```env
SECRET_KEY=your-secret-key-here
DEBUG=True
OPENAI_API_KEY=your-openai-api-key
GEMINI_API_KEY=your-gemini-api-key
```

**Note**: Your API keys are already configured in the `.env` file.

### 5. Install and Start Redis

**Download Redis for Windows**:
- Download from: https://github.com/microsoftarchive/redis/releases
- Or use Memurai (Redis alternative): https://www.memurai.com/

**Start Redis**:
```powershell
# If using Redis
redis-server

# Or if using Memurai
# Start Memurai from Windows Services
```

Verify Redis is running:
```powershell
redis-cli ping
# Should return: PONG
```

### 6. Create Required Directories

```powershell
# Create logs directory
New-Item -ItemType Directory -Force -Path logs

# Create media directory for PDF uploads
New-Item -ItemType Directory -Force -Path media\uploads

# Create ChromaDB directory
New-Item -ItemType Directory -Force -Path chromadb_data
```

### 7. Run Migrations

```powershell
python manage.py makemigrations
python manage.py makemigrations accounts
python manage.py makemigrations students
python manage.py makemigrations superadmin
python manage.py migrate
```

### 8. Create Superuser

```powershell
python manage.py createsuperuser
```

Follow the prompts to create a superadmin account. Make sure to set the `role` field to `super_admin` after creation.

## 🏃‍♂️ Running the Application

You need to run **three** processes simultaneously:

### Terminal 1: Django Development Server

```powershell
python manage.py runserver
```

Access the application at: http://localhost:8000

### Terminal 2: Celery Worker

```powershell
celery -A ncert_project worker --loglevel=info --pool=solo
```

**Note**: Use `--pool=solo` on Windows to avoid issues with the default pool.

### Terminal 3: Celery Beat (Optional - for scheduled tasks)

```powershell
celery -A ncert_project beat --loglevel=info
```

## 📚 Usage Guide

### For Superadmins

1. **Login** as superadmin at http://localhost:8000/accounts/login/
2. **Upload PDFs**:
   - Navigate to Superadmin Dashboard
   - Click "Upload New PDF"
   - Drag and drop or select a PDF file
   - Map to Standard (5-10), Subject, and Chapter
   - Click "Upload & Process"
3. **Monitor Processing**:
   - View dashboard for status statistics
   - Check "All Uploads" for detailed list
   - Click "View" on any upload for detailed information

### For Students

1. **Register** at http://localhost:8000/accounts/register/
2. **Login** and access Student Dashboard
3. **Chat with AI Tutor**:
   - Click "AI Tutor" or "Start Chat"
   - Select AI model (OpenAI or Gemini)
   - Ask questions about NCERT curriculum
   - View chat history on dashboard

## 🏗️ Project Structure

```
new-intel-ncert/
├── ncert_project/          # Main Django project
│   ├── settings.py         # Configuration with API keys, ChromaDB, Celery
│   ├── urls.py             # URL routing
│   ├── celery.py           # Celery configuration
│   └── wsgi.py
├── accounts/               # User authentication app
│   ├── models.py           # CustomUser model with roles
│   └── views.py
├── students/               # Student features app
│   ├── models.py           # ChatHistory, StudentProfile
│   ├── views.py            # Chatbot logic with RAG
│   └── urls.py
├── superadmin/             # Admin features app
│   ├── models.py           # UploadedBook model
│   ├── views.py            # Upload management
│   ├── tasks.py            # Celery tasks for PDF processing
│   └── urls.py
├── templates/              # HTML templates
│   ├── base_new.html       # Base template with Tailwind CSS
│   ├── home.html           # Landing page
│   ├── students/           # Student templates
│   │   ├── chatbot.html    # AI chat interface
│   │   └── dashboard.html
│   └── superadmin/         # Superadmin templates
│       ├── dashboard.html
│       ├── upload.html     # Drag-and-drop upload
│       ├── upload_list.html
│       └── upload_detail.html
├── media/                  # Uploaded PDFs
├── chromadb_data/          # Vector database storage
├── logs/                   # Application logs
├── requirements.txt        # Python dependencies
├── .env                    # Environment variables (DO NOT COMMIT)
└── .gitignore
```

## 🔧 Configuration

### Key Settings (in `settings.py`)

- **Database**: SQLite (for development)
- **ChromaDB**: Persistent storage in `chromadb_data/`
- **Celery**: Redis broker at `redis://localhost:6379/0`
- **Media Files**: Stored in `media/uploads/`
- **Logging**: Comprehensive logging to `logs/django.log`

### Embedding Model

The system uses `sentence-transformers` with the `all-MiniLM-L6-v2` model for:
- Free, local embeddings (no API costs)
- Fast processing
- Good performance for educational content

## 🐛 Troubleshooting

### Redis Connection Error

```
Error: Error 61 connecting to localhost:6379. Connection refused.
```

**Solution**: Make sure Redis is running:
```powershell
redis-server
```

### Celery Import Error

```
ImportError: cannot import name 'soft_unicode' from 'markupsafe'
```

**Solution**: Already fixed in requirements.txt with `MarkupSafe==2.0.1`

### PDF Processing Stuck

1. Check Celery worker is running
2. Check Redis is running
3. View logs: `logs/django.log`
4. Check upload status in superadmin dashboard

### ChromaDB Persistence Issues

Ensure the `chromadb_data/` directory exists and has write permissions:
```powershell
New-Item -ItemType Directory -Force -Path chromadb_data
```

## 📊 Technology Stack

- **Backend**: Django 2.2.28
- **Database**: SQLite (development), PostgreSQL (production ready)
- **Vector DB**: ChromaDB 0.4.22
- **Task Queue**: Celery 5.3.4 + Redis
- **AI Models**: 
  - OpenAI GPT-4o-mini
  - Google Gemini 1.5 Flash
- **Embeddings**: sentence-transformers (all-MiniLM-L6-v2)
- **PDF Processing**: pdfplumber, PyPDF2
- **Frontend**: Tailwind CSS, Alpine.js, Font Awesome
- **Text Chunking**: LangChain

## 🔐 Security

- **Environment Variables**: API keys stored in `.env` (not committed)
- **CSRF Protection**: Enabled for all POST requests
- **User Authentication**: Required for all features
- **Role-Based Access**: Superadmin vs Student permissions
- **File Validation**: PDF-only uploads with size limits

## 🚀 Deployment (Production)

### Additional Steps for Production

1. **Set `DEBUG=False`** in `.env`
2. **Configure ALLOWED_HOSTS** in `settings.py`
3. **Use PostgreSQL** instead of SQLite
4. **Collect static files**:
   ```bash
   python manage.py collectstatic
   ```
5. **Use Gunicorn** as WSGI server:
   ```bash
   gunicorn ncert_project.wsgi:application
   ```
6. **Setup Nginx** as reverse proxy
7. **Use Supervisor** to manage Celery workers
8. **Setup SSL** with Let's Encrypt

## 📝 API Keys Required

1. **OpenAI API Key**: Get from https://platform.openai.com/api-keys
2. **Google Gemini API Key**: Get from https://makersuite.google.com/app/apikey

Add both to your `.env` file (already configured in your project).

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Open a Pull Request

## 📄 License

This project is licensed under the MIT License.

## 👥 Support

For issues or questions:
- GitHub Issues: https://github.com/Winterbear0701/ncert-working/issues
- Email: [Your Email]

## 🎉 Acknowledgments

- NCERT for educational content
- OpenAI and Google for AI models
- Django and Python communities

---

**Made with ❤️ for Indian Students**
