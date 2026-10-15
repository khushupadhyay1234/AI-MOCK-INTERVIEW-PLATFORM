import os
import re
import sqlite3
import hashlib

import streamlit as st
from dotenv import load_dotenv
from groq import Groq
from PyPDF2 import PdfReader

load_dotenv(override=True)
st.set_page_config(page_title="AI Mock Interview Platform", page_icon="🎯", layout="wide")
MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
API_KEY = os.getenv("GROQ_API_KEY", "")

@st.cache_resource
def get_db():
    connection = sqlite3.connect("interview_history.db", check_same_thread=False)
    connection.execute("""CREATE TABLE IF NOT EXISTS interviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        company TEXT,
        technical_score REAL,
        communication_score REAL,
        problem_solving_score REAL,
        score TEXT,
        date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )""")
    for column in ("technical_score", "communication_score", "problem_solving_score", "confidence_score", "ats_score"):
        columns = [r[1] for r in connection.execute("PRAGMA table_info(interviews)")]
        if column not in columns:
            connection.execute(f"ALTER TABLE interviews ADD COLUMN {column} REAL")
    connection.commit()
    return connection

DB = get_db()
DEFAULTS = {
    "resume_hash": None, "resume_text": "", "detected_skills": "", "skills_input": "",
    "ats_result": "", "questions": [], "current_question": 0,
    "answers": [], "interview_started": False, "evaluation_done": False,
    "last_feedback": "", "overall_report": "", "learning_roadmap": "",
    "weak_analysis": "", "saved_to_db": False, "interview_company": "",
}
for key, value in DEFAULTS.items():
    if key not in st.session_state:
        st.session_state[key] = value


def ask_groq(prompt, system="You are a helpful, precise technical interviewer."):
    """Call Groq, retrying with a second supported GPT-OSS model for empty output.

    API errors are intentionally surfaced rather than mistaken for empty output.
    """
    if not API_KEY:
        raise RuntimeError("GROQ_API_KEY is missing. Add it to your .env file and restart Streamlit.")

    client = Groq(api_key=API_KEY)
    fallback = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-120b").strip()
    candidates = list(dict.fromkeys([MODEL, fallback]))
    diagnostics = []

    for model_id in candidates:
        options = {
            "model": model_id,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": prompt},
            ],
            "max_completion_tokens": 4096,
            "temperature": 0.2,
        }
        if model_id.startswith("openai/gpt-oss-"):
            options["reasoning_effort"] = "low"
            options["include_reasoning"] = False

        # Only retry on successful API responses that contain no usable text.
        # Authentication, access, and rate-limit failures should be displayed as-is.
        response = client.chat.completions.create(**options)
        if not response.choices:
            diagnostics.append(f"{model_id}: no choices returned")
            continue
        choice = response.choices[0]
        result = (choice.message.content or "").strip()
        if result:
            return result
        diagnostics.append(
            f"{model_id}: empty content, finish_reason={choice.finish_reason}, "
            f"usage={response.usage}"
        )

    raise RuntimeError("Groq returned empty responses: " + " | ".join(diagnostics))


def reset_interview():
    for key, value in {
        "questions": [], "current_question": 0, "answers": [],
        "interview_started": False, "evaluation_done": False,
        "last_feedback": "", "overall_report": "", "learning_roadmap": "",
        "weak_analysis": "", "saved_to_db": False, "interview_company": "",
    }.items():
        st.session_state[key] = value


def score_from_report(text, label):
    match = re.search(rf"{re.escape(label)}\s*:\s*\**\s*(\d+(?:\.\d+)?)", text, re.I)
    if not match:
        return None
    return max(0.0, min(10.0, float(match.group(1))))


def parse_questions(raw):
    questions = []
    for line in raw.splitlines():
        found = re.match(r"^\s*(?:[1-5][.)]|Q[1-5][.:])\s*(.+)", line.strip(), re.I)
        if found:
            questions.append(found.group(1).strip())
    return questions[:5]


def create_final_report():
    answers = "\n\n".join(
        f"Question: {x['question']}\nCandidate answer: {x['answer']}\nFeedback: {x['feedback']}"
        for x in st.session_state.answers
    )
    prompt = f"""You are a senior hiring manager. Evaluate the COMPLETE interview, not individual
questions. Base judgments only on the candidate's actual responses. Give scores from 0 to 10.
Return these labels exactly:
Technical Score: X.X
Communication Score: X.X
Problem Solving Score: X.X
Strong Areas:
- ...
Weak Areas:
- ...
Topics To Improve:
- ...
Final Verdict: Hire / Borderline / Reject

Interview evidence:\n{answers}"""
    report = ask_groq(prompt)
    st.session_state.overall_report = report
    try:
        st.session_state.learning_roadmap = ask_groq(
            "Using this interview report, give strong topics, weak topics, a realistic "
            "weekly revision plan, priority DSA topics, and priority CS subjects:\n" + report
        )
    except Exception as exc:
        st.session_state.learning_roadmap = f"Roadmap unavailable: {exc}"
    try:
        st.session_state.weak_analysis = ask_groq(
            "From this interview report, identify weak DSA topics, weak CS subjects, "
            "topic-wise scores out of 10 (only if supported), and what to revise first:\n" + report
        )
    except Exception as exc:
        st.session_state.weak_analysis = f"Weak topic analysis unavailable: {exc}"


st.sidebar.title("🎯 AI Interviewer")
st.sidebar.write("Practice for placements with AI-powered interviews.")
st.sidebar.caption(f"Model: {MODEL}")
if st.sidebar.button("Test Groq Connection"):
    try:
        answer = ask_groq("Reply with exactly: API Working")
        st.sidebar.success(f"Groq response: {answer}")
    except Exception as exc:
        st.sidebar.error(f"Groq connection failed: {exc}")
st.title("AI Mock Interview Platform")
st.header("Placement Preparation Platform")
if not API_KEY:
    st.error("Missing GROQ_API_KEY. Create a .env file with GROQ_API_KEY=your_key_here.")

uploaded_file = st.file_uploader("Upload Resume (PDF)", type=["pdf"])
if uploaded_file is not None:
    file_bytes = uploaded_file.getvalue()
    file_hash = hashlib.sha256(file_bytes).hexdigest()
    if file_hash != st.session_state.resume_hash:
        try:
            from io import BytesIO
            reader = PdfReader(BytesIO(file_bytes))
            text = "\n".join(page.extract_text() or "" for page in reader.pages).strip()
            if not text:
                st.warning("No selectable PDF text found. Use a text-based resume PDF.")
            st.session_state.resume_text = text
            st.session_state.resume_hash = file_hash
            st.session_state.detected_skills = ""
            st.session_state.skills_input = ""
            st.session_state.ats_result = ""
            reset_interview()
        except Exception as exc:
            st.error(f"Error reading PDF: {exc}")
    if st.session_state.resume_text:
        st.success("✅ Resume uploaded successfully")
        if st.button("Analyze Resume and Extract Skills"):
            # Independent calls: ATS failure cannot prevent skills extraction.
            try:
                with st.spinner("Extracting technical skills..."):
                    extracted = ask_groq(
                        "Extract ONLY technical skills explicitly present in the resume. "
                        "Include programming languages, frameworks, databases, tools, "
                        "and technical concepts. Return ONLY a comma-separated list "
                        "with no headings or extra text.\nResume:\n"
                        + st.session_state.resume_text[:8000]
                    )
                    st.session_state.detected_skills = extracted
                    st.session_state.skills_input = extracted
                st.success("Technical skills extracted successfully!")
            except Exception as exc:
                st.error(f"Skill Extraction Error: {exc}")

            try:
                with st.spinner("Analyzing resume..."):
                    st.session_state.ats_result = ask_groq(
                        "Evaluate this resume for software engineering placements. Return "
                        "an estimated ATS Score (0-100), Strengths, Weaknesses, and "
                        "Missing Keywords. This is an advisory estimate, not a real "
                        "ATS system.\nResume:\n"
                        + st.session_state.resume_text[:5000]
                    )
            except Exception as exc:
                st.warning(f"ATS Analysis Error: {exc}")
        if st.session_state.ats_result:
            st.subheader("📄 ATS Resume Analysis")
            st.write(st.session_state.ats_result)
else:
    if st.session_state.resume_hash is not None:
        st.session_state.resume_hash = None
        st.session_state.resume_text = ""
        st.session_state.detected_skills = ""
        st.session_state.ats_result = ""
        st.session_state.skills_input = ""
        reset_interview()

if "skills_input" not in st.session_state:
    st.session_state.skills_input = st.session_state.detected_skills
skills = st.text_area("Detected Skills (Edit if Needed)", key="skills_input", height=120)
company = st.selectbox("Select Company", ["Google", "Amazon", "Microsoft", "Adobe", "Flipkart", "Walmart", "Goldman Sachs", "JP Morgan", "Atlassian", "Uber"])
level = st.selectbox("Interview Difficulty", ["Easy", "Medium", "Hard"])
topic = st.selectbox("Select DSA Topic", ["Arrays", "Binary Search", "Trees", "Graphs", "Dynamic Programming"])

if st.button("Generate Interview Questions"):
    if not st.session_state.resume_text:
        st.warning("Please upload a readable resume first.")
    elif not skills.strip():
        st.warning("Please enter or extract skills first.")
    else:
        prompt = f"""Generate EXACTLY five distinct technical interview questions for {company}.
Difficulty: {level}. Selected DSA Topic: {topic}.
Q1: candidate's resume project; Q2: deeper follow-up on that project;
Q3: candidate skills; Q4: coding question from {topic};
Q5: representative {company}-style technical question.
No HR questions. Output ONLY five single-line numbered questions (1. through 5.).
Resume:\n{st.session_state.resume_text[:2500]}\nSkills:\n{skills[:800]}"""
        try:
            with st.spinner("Generating Questions..."):
                raw = ask_groq(prompt)
                questions = parse_questions(raw)
                if len(questions) != 5:
                    st.error("The model did not return five correctly numbered questions. Please retry.")
                    st.code(raw)
                else:
                    reset_interview()
                    st.session_state.questions = questions
                    st.session_state.interview_company = company
                    st.session_state.interview_started = True
                    st.success("Interview generated successfully.")
        except Exception as exc:
            st.error(f"Question Generation Error: {exc}")

st.divider()
st.subheader("Answer Evaluation")
if st.session_state.interview_started:
    idx = st.session_state.current_question
    if idx < len(st.session_state.questions):
        question = st.session_state.questions[idx]
        st.subheader(f"Question {idx + 1} of {len(st.session_state.questions)}")
        st.info(question)
        st.progress((idx + 1) / len(st.session_state.questions))
        answer_key = f"answer_{idx}"
        answer = st.text_area("Write Your Answer Here", key=answer_key, height=220)
        if not st.session_state.evaluation_done:
            if st.button("Evaluate Answer"):
                if len(answer.strip()) < 20:
                    st.warning("Please write a more detailed answer (at least 20 characters).")
                else:
                    evaluation_prompt = f"""You are a strict technical interviewer. Evaluate only
what the candidate actually wrote. Do not invent missing code or explanations.
Give scores from 0 to 10. Penalize inaccurate, irrelevant, or vague answers.
Question: {question}\nCandidate Answer: {answer}
Return exactly these labels and supporting points:
Technical Score: X.X
Communication Score: X.X
Problem Solving Score: X.X
Strong Areas:
- ...
Weak Areas:
- ...
Topics To Improve:
- ...
Final Verdict: Hire / Borderline / Reject"""
                    try:
                        with st.spinner("Evaluating Answer..."):
                            feedback = ask_groq(evaluation_prompt)
                            st.session_state.answers.append({"question": question, "answer": answer, "feedback": feedback})
                            st.session_state.last_feedback = feedback
                            st.session_state.evaluation_done = True
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Answer Evaluation Error: {exc}")
        else:
            st.subheader("AI Feedback")
            st.write(st.session_state.last_feedback)
            if st.button("Next Question" if idx < 4 else "Finish Interview"):
                st.session_state.current_question += 1
                st.session_state.evaluation_done = False
                st.session_state.last_feedback = ""
                st.rerun()
    else:
        st.success("🎉 Interview Completed")
        if not st.session_state.overall_report:
            if st.button("Generate Final Report"):
                try:
                    with st.spinner("Creating final report and roadmap..."):
                        create_final_report()
                    st.rerun()
                except Exception as exc:
                    st.error(f"Report Generation Error: {exc}")

if st.session_state.overall_report:
    report = st.session_state.overall_report
    labels = ("Technical Score", "Communication Score", "Problem Solving Score")
    scores = [score_from_report(report, label) for label in labels]
    cols = st.columns(3)
    for col, label, score in zip(cols, labels, scores):
        col.metric(label, f"{score:.1f}/10" if score is not None else "N/A")
    st.subheader("📊 Final Interview Report")
    st.markdown(report)
    st.download_button("📥 Download Report", data=report, file_name="interview_report.txt", mime="text/plain")
    if all(score is not None for score in scores):
        average = sum(scores) / 3
        st.progress(average / 10)
        st.success(f"Overall Interview Score: {average:.1f}/10")
    if st.session_state.learning_roadmap:
        st.subheader("📚 Learning Roadmap")
        st.write(st.session_state.learning_roadmap)
    if st.session_state.weak_analysis:
        st.subheader("📉 Weak Topic Analysis")
        st.write(st.session_state.weak_analysis)
    if not st.session_state.saved_to_db:
        try:
            DB.execute("""INSERT INTO interviews(company, technical_score, communication_score,
                        problem_solving_score, score) VALUES (?, ?, ?, ?, ?)""",
                       (st.session_state.interview_company, *scores, report))
            DB.commit()
            st.session_state.saved_to_db = True
        except Exception as exc:
            st.error(f"Could not save interview: {exc}")

if st.session_state.answers:
    st.header("Interview Summary")
    for idx, item in enumerate(st.session_state.answers, start=1):
        with st.expander(f"Question {idx}"):
            st.write(item["question"])
            st.markdown("**Your Answer:**")
            st.write(item["answer"])
            st.markdown("**Feedback:**")
            st.write(item["feedback"])

st.sidebar.subheader("Past Interviews")
try:
    for company_name, date in DB.execute("SELECT company, date FROM interviews ORDER BY id DESC LIMIT 10"):
        st.sidebar.write(f"{company_name} — {date}")
except Exception as exc:
    st.sidebar.error(f"Could not load history: {exc}")
st.divider()
st.caption("Built using Streamlit + Groq LLM + SQLite for placement preparation")
