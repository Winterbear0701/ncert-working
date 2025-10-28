# Unit Test Evaluation System - Complete Guide

## 🎯 Overview

The NCERT Learning Platform now features an **advanced AI-powered unit test evaluation system** that provides accurate, consistent, and fair grading for both short and long-answer questions.

## ✨ Key Features

### 1. **Smart Question Type Detection**
- **1-Mark Questions**: Case-insensitive exact matching (ignores punctuation, whitespace, and case)
- **2-5 Mark Questions**: AI-powered evaluation with detailed feedback

### 2. **Dual Scoring System for Long Answers**
- **Content Score (70% weight)**: How well the answer matches key concepts from the model answer
- **Grammar Score (30% weight)**: Language quality, sentence structure, and clarity

### 3. **Multi-Model AI Support**
- **Gemini 2.0 Flash** (Default): Fast and accurate
- **OpenAI GPT-4o-mini**: Alternative high-quality option
- Automatic fallback if primary model fails

### 4. **Comprehensive Feedback**
- Question-by-question detailed feedback
- Overall performance summary
- Personalized improvement recommendations
- Score breakdowns with percentages

---

## 📊 How Evaluation Works

### For 1-Mark Questions (Short Answer)

**Evaluation Method**: Case-insensitive exact match

**Example:**
```
Model Answer: "Photosynthesis"
Student Answers That Get Full Marks:
✓ "photosynthesis"
✓ "PHOTOSYNTHESIS"
✓ "Photosynthesis."
✓ "  photosynthesis  "

Student Answers That Get Zero:
✗ "Photo synthesis" (extra space)
✗ "process of photosynthesis" (extra words)
```

**Why This Approach?**
- Fair: Students shouldn't lose marks for capitalization or punctuation in short answers
- Clear: Either correct or incorrect, no ambiguity
- Fast: Instant evaluation without AI overhead

---

### For 2-5 Mark Questions (Long Answer)

**Evaluation Method**: AI-powered content and grammar analysis

**Scoring Formula:**
```
Total Marks = (Content Score × 0.7 + Grammar Score × 0.3) × Question Marks
```

#### Content Evaluation (70%)

The AI compares the student's answer with the **model answer provided by staff** and checks:
- ✅ All key concepts covered
- ✅ Factual accuracy
- ✅ Depth and completeness
- ✅ Understanding demonstrated

**Scoring Guide:**
- **90-100%**: Excellent - All key points covered accurately
- **70-89%**: Good - Most key points covered
- **50-69%**: Average - Some key points missing
- **30-49%**: Below Average - Significant gaps
- **0-29%**: Poor - Major concepts missing

#### Grammar Evaluation (30%)

The AI assesses language quality:
- ✅ Sentence structure
- ✅ Grammar correctness
- ✅ Punctuation and capitalization
- ✅ Spelling accuracy
- ✅ Clarity and coherence

**Scoring Guide:**
- **90-100%**: Excellent - Perfect or near-perfect
- **70-89%**: Good - Minor errors
- **50-69%**: Average - Several errors but understandable
- **30-49%**: Below Average - Frequent errors
- **0-29%**: Poor - Major grammar issues

---

## 🎓 Example Evaluation

### Question (5 marks)
**"Explain the process of photosynthesis."**

### Model Answer (Provided by Staff)
```
Photosynthesis is the process by which green plants make their own food using 
sunlight, water, and carbon dioxide. Chlorophyll in the leaves absorbs sunlight. 
The plant takes in carbon dioxide from the air and water from the soil. Using 
the energy from sunlight, these are converted into glucose (food) and oxygen. 
The oxygen is released into the air.
```

### Student Answer 1 (High Score)
```
Photosynthesis is the process where green plants produce food. Plants use 
sunlight, carbon dioxide from air, and water from soil. Chlorophyll in leaves 
captures sunlight energy. This energy converts CO2 and water into glucose 
which is food for the plant. Oxygen is produced and released as a byproduct.
```

**AI Evaluation:**
- Content Score: 95% (All key concepts covered, excellent understanding)
- Grammar Score: 90% (Well-written, minor room for improvement)
- **Total: 4.58/5 marks**

**Feedback:**
```
📊 Score Breakdown:
• Content: 3.32/3.5 marks (95%)
• Grammar & Expression: 1.35/1.5 marks (90%)
• Total: 4.58/5 marks

Excellent answer! You've covered all the key concepts of photosynthesis clearly. 
Your explanation of the inputs (sunlight, CO2, water) and outputs (glucose, oxygen) 
is accurate. The role of chlorophyll is correctly mentioned. Your sentences are 
clear and well-structured.

Minor suggestion: You could mention that chlorophyll is specifically what makes 
leaves green to add more detail.
```

### Student Answer 2 (Medium Score)
```
photosynthesis is when plants make food they use sun and water and co2 to 
make food and give oxygen
```

**AI Evaluation:**
- Content Score: 60% (Basic concepts covered but lacks detail)
- Grammar Score: 40% (Poor sentence structure, capitalization issues)
- **Total: 2.7/5 marks**

**Feedback:**
```
📊 Score Breakdown:
• Content: 2.1/3.5 marks (60%)
• Grammar & Expression: 0.6/1.5 marks (40%)
• Total: 2.7/5 marks

You have the basic idea of photosynthesis, which is good! However, your answer 
needs more detail. Missing key points:
- Role of chlorophyll in capturing sunlight
- Where water comes from (soil/roots)
- The specific product name (glucose, not just "food")

Grammar improvements needed:
- Start sentences with capital letters
- Use proper punctuation (periods, commas)
- Write in complete sentences instead of run-on sentences
- Example: "Photosynthesis is the process where plants make food. They use..."
```

---

## 🔧 How Staff Creates Questions

When creating a unit test, staff provides:

1. **Question Text**: The actual question
2. **Model Answer**: The expected correct answer (this is crucial!)
3. **Marks**: 1, 2, 3, 4, or 5

**Example Setup:**
```
Question Number: 1
Marks: 1
Question: "What is the powerhouse of the cell?"
Model Answer: "Mitochondria"

Question Number: 2
Marks: 3
Question: "Explain the function of mitochondria in a cell."
Model Answer: "Mitochondria are known as the powerhouse of the cell. They 
produce energy in the form of ATP through cellular respiration. They break 
down glucose and oxygen to release energy that the cell needs for various 
functions."
```

---

## ⚙️ Configuration Options

### Choosing AI Model

You can set the default AI model in your `.env` file:

```bash
# Use Gemini (default, recommended)
DEFAULT_EVAL_AI=gemini

# Or use OpenAI
DEFAULT_EVAL_AI=openai
```

### API Keys Required

Make sure these are set in your `.env`:
```bash
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
```

**Note**: The system will automatically fallback if one model fails:
- If Gemini fails → tries OpenAI
- If OpenAI fails → tries Gemini
- If both fail → uses heuristic scoring

---

## 📈 Evaluation Report Features

After evaluation, students see:

### 1. Overall Summary
```
📊 UNIT TEST EVALUATION SUMMARY
================================================
🎯 Overall Score: 68.5/100 (68.5%)
📝 Content Accuracy: 72%
✍️ Grammar & Expression: 65%
🤖 Evaluated by: GEMINI AI

📌 1-Mark Questions: 15/20 correct (75%)
📝 Long-Answer Questions: 23.5/40 (59%)
```

### 2. Performance Feedback
Based on percentage:
- **90%+**: Outstanding Performance
- **75-89%**: Great Job
- **60-74%**: Good Effort
- **40-59%**: Keep Improving
- **<40%**: Don't Give Up

### 3. Personalized Recommendations

If content score is low (<60%):
```
📖 Content Focus:
• Review the model answers carefully
• Include all important concepts
• Practice explaining in your own words
```

If grammar score is low (<70%):
```
✏️ Language Improvement:
• Work on sentence structure
• Use proper punctuation
• Write in clear, complete sentences
```

### 4. Question-by-Question Breakdown

Each answer shows:
- Marks awarded
- Content and grammar scores
- Detailed AI feedback
- Improvement suggestions

---

## 🔍 Technical Details

### Files Modified

1. **`superadmin/evaluate.py`**
   - Enhanced `exact_match_score()` for better 1-mark evaluation
   - Improved `ai_evaluate()` with detailed rubric
   - Added multi-model support
   - Better error handling and caching

2. **`students/unit_test_evaluator.py`**
   - Updated to use new evaluation system
   - Added AI model selection
   - Enhanced feedback generation
   - Better statistics tracking

3. **`students/views.py`**
   - Modified `unit_test_submit()` to support AI model selection

### Database Fields

The `UnitTestAnswer` model stores:
```python
awarded_marks        # Total marks awarded
content_score        # Content accuracy (0-1)
grammar_score        # Grammar quality (0-1)
ai_feedback          # Detailed feedback
evaluation_type      # 'exact', 'ai', or 'heuristic'
evaluation_model     # 'gemini', 'openai', or 'none'
evaluated_at         # Timestamp
```

### Caching System

To avoid re-evaluating identical answers:
- Cache key includes: student answer + model answer + marks + AI model
- Cache duration: 2 hours
- Significantly reduces API costs and evaluation time

---

## 🧪 Testing the System

### Test Case 1: 1-Mark Question
```python
Question: "What is the capital of India?"
Model Answer: "New Delhi"

Student Answers:
"new delhi"      → 1/1 ✓
"NEW DELHI"      → 1/1 ✓
"New Delhi."     → 1/1 ✓
"  new delhi  "  → 1/1 ✓
"Delhi"          → 0/1 ✗
"New Delhi city" → 0/1 ✗
```

### Test Case 2: 3-Mark Question
```python
Question: "What are the three states of matter?"
Model Answer: "The three states of matter are solid, liquid, and gas. In solids, 
particles are tightly packed. In liquids, particles are loosely packed. In gases, 
particles are far apart."

Test with various student answers to see different scores!
```

---

## 💡 Best Practices

### For Students
1. **Read carefully**: Understand what the question asks
2. **Include key points**: Cover all important concepts from your textbook
3. **Write clearly**: Use proper grammar, punctuation, and spelling
4. **Be complete**: For long answers, explain thoroughly
5. **Review before submit**: Check for errors

### For Staff/Teachers
1. **Write clear model answers**: These are the reference for AI evaluation
2. **Include all key points**: The AI looks for these in student answers
3. **Be comprehensive**: Especially for higher-mark questions
4. **Use proper language**: Model answers set the standard
5. **Test questions**: Try with sample student answers to verify

### For Administrators
1. **Monitor API usage**: Check API quotas for Gemini/OpenAI
2. **Review evaluations**: Periodically check if AI is grading fairly
3. **Adjust weights**: If needed, modify content/grammar ratio
4. **Keep model answers updated**: Ensure they match current curriculum

---

## 🐛 Troubleshooting

### Issue: All answers getting 0 marks
**Solution**: Check if model answers are properly saved in the database

### Issue: Evaluation fails
**Solution**: 
1. Verify API keys in `.env`
2. Check API quota/limits
3. Review logs for specific error messages

### Issue: Inconsistent grading
**Solution**: 
1. Ensure model answers are detailed and clear
2. Try switching AI models
3. Check if caching is causing issues (clear cache)

### Issue: Grammar scores too harsh
**Solution**: The 30% weight ensures grammar doesn't dominate. This is balanced for Indian school standards.

---

## 📞 Support

For questions or issues:
1. Check this documentation
2. Review the code comments in `superadmin/evaluate.py`
3. Check application logs for detailed error messages
4. Test with simple questions first before complex ones

---

## 🎉 Summary

The new evaluation system provides:
- ✅ Fair and consistent grading
- ✅ Detailed feedback for improvement
- ✅ Separate content and grammar assessment
- ✅ Smart handling of different question types
- ✅ Reliable AI with fallback options
- ✅ Comprehensive reporting for students

This ensures students get meaningful feedback while maintaining academic standards!
