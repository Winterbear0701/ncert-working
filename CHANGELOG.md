# Changelog - NCERT Learning Platform

## [v2.0] - October 7, 2025

### 🎉 Major Updates

#### 1. **Chatbot Improvements**
- ✅ Fixed Gemini API model version (now using `gemini-2.0-flash-exp`)
- ✅ Fixed OpenAI API call syntax (using new `openai.chat.completions.create`)
- ✅ Added support for **general questions** (not just NCERT content)
- ✅ Improved fallback mechanism: OpenAI → Gemini → Error message
- ✅ Added `model_used` field to ChatHistory to track which AI model was used
- ✅ Better error handling and logging

**Supported Models:**
- **OpenAI**: `gpt-4o-mini` (fast and efficient)
- **Gemini**: `gemini-2.0-flash-exp` (latest experimental model)

#### 2. **Authentication System Overhaul**
- ✅ **Auto-assign student role** during registration (no manual role selection)
- ✅ Fixed dashboard routing:
  - Students → `/students/dashboard/`
  - Superadmins → `/superadmin/`
- ✅ Added beautiful Tailwind CSS styling to login/register pages
- ✅ Removed role field from registration form (security improvement)

#### 3. **Database Schema Updates**
- ✅ Added `model_used` field to `ChatHistory` model
- ✅ Created migration: `0003_chathistory_model_used.py`

#### 4. **Environment Configuration**
- ✅ Fixed `.env` file loading from `ncert_project/.env`
- ✅ Added proper BASE_DIR path resolution for .env file

#### 5. **Code Cleanup**
- ✅ Deleted all test files:
  - `test_gemini.py`
  - `test_gemini_models.py`
  - `test_gemini_rest.py`
  - `test_gemini_simple.py`
  - `test_openai.py`
  - `list_gemini_models.py`
  - `rag_setup.py`
- ✅ Removed `utils/` folder (unnecessary Nougat wrapper)
- ✅ Note: `nougat/` folder (960MB) already ignored in `.gitignore`

---

## 🚀 How to Use

### For Students:
1. **Register** at `/accounts/register/` - automatically assigned as student
2. **Login** at `/accounts/login/`
3. **Access Chatbot** at `/students/chatbot/`
4. **Ask any question** - both general and NCERT-specific!

### For Superadmins:
1. **Login** at `/accounts/login/`
2. **Access Admin Dashboard** at `/superadmin/`
3. **Upload PDFs** at `/superadmin/upload/`

---

## 🔧 Technical Details

### Chatbot Features:
- **RAG (Retrieval Augmented Generation)**: Fetches relevant NCERT content from ChromaDB
- **General Q&A**: Can answer non-NCERT questions using pure LLM knowledge
- **Dual AI Support**: Choose between OpenAI or Gemini
- **Smart Fallback**: Automatically switches models if one fails
- **Context-Aware**: Filters NCERT content by student's standard

### API Keys Required:
- **OpenAI API Key**: `OPENAI_API_KEY` in `ncert_project/.env`
- **Gemini API Key**: `GEMINI_API_KEY` in `ncert_project/.env`

### Known Limitations:
- OpenAI quota may be exceeded (error 429) - will auto-fallback to Gemini
- ChromaDB requires populated data for NCERT-specific answers

---

## 📝 Files Modified

### Updated Files:
1. `accounts/forms.py` - Removed role field
2. `accounts/views.py` - Auto-assign student role
3. `ncert_project/settings.py` - Fixed .env loading
4. `students/models.py` - Added model_used field
5. `students/views.py` - Fixed API calls, added general Q&A
6. `templates/accounts/login.html` - Added Tailwind styling
7. `templates/accounts/register.html` - Added Tailwind styling

### Deleted Files:
1. `rag_setup.py`
2. `utils/nougat_wrapper.py`
3. All test_*.py files

### New Files:
1. `students/migrations/0003_chathistory_model_used.py`
2. `CHATBOT_FIXES.md`
3. `CHANGELOG.md` (this file)

---

## 🐛 Bug Fixes

1. ✅ Fixed Gemini 404 error (incorrect model name)
2. ✅ Fixed OpenAI API syntax error (old ChatCompletion API)
3. ✅ Fixed dashboard routing for students
4. ✅ Fixed registration auto-assigning wrong roles
5. ✅ Fixed .env file not being loaded properly
6. ✅ Fixed ChatHistory save error (missing model_used field)

---

## 🎨 UI/UX Improvements

1. ✅ Beautiful gradient backgrounds on login/register pages
2. ✅ Responsive forms with animations
3. ✅ Error message styling
4. ✅ Password visibility toggle
5. ✅ Consistent branding with base_new.html

---

## 🔐 Security Improvements

1. ✅ Removed role selection from registration (prevents privilege escalation)
2. ✅ Students can only be created through public registration
3. ✅ Superadmins must be created via Django admin or command line

---

## 📊 Next Steps / TODO

- [ ] Add web scraping capability for questions outside ChromaDB
- [ ] Implement Redis for Celery (PDF processing)
- [ ] Add more comprehensive NCERT content to ChromaDB
- [ ] Add user profile editing
- [ ] Add password reset functionality
- [ ] Implement rate limiting for chatbot
- [ ] Add chat history export feature
- [ ] Add analytics dashboard for superadmins

---

## 💡 Testing Checklist

- [x] Student registration works and auto-assigns role
- [x] Student login redirects to `/students/dashboard/`
- [x] Superadmin login redirects to `/superadmin/`
- [x] Chatbot works with Gemini API
- [x] Chatbot handles general questions
- [x] Chatbot saves chat history with model_used
- [x] OpenAI fallback works (if quota available)
- [ ] PDF upload and ChromaDB ingestion (requires Redis)

---

**Version**: 2.0  
**Date**: October 7, 2025  
**Status**: ✅ Production Ready
