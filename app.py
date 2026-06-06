import streamlit as st
import sqlite3
from groq import Groq
from PyPDF2 import PdfReader
from dotenv import load_dotenv
import os
import re

# ----------------------------------
# Load Environment Variables
# ----------------------------------
load_dotenv()

conn = sqlite3.connect(
    "interview_history.db",
    check_same_thread=False
)

cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS interviews(
id INTEGER PRIMARY KEY AUTOINCREMENT,
company TEXT,
technical_score REAL,
communication_score REAL,
problem_solving_score REAL,
score TEXT,
date TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
""")

# Database migration for older versions
cursor.execute("PRAGMA table_info(interviews)")
existing_columns = [col[1] for col in cursor.fetchall()]

if "technical_score" not in existing_columns:
    cursor.execute(
        "ALTER TABLE interviews ADD COLUMN technical_score REAL"
    )

if "communication_score" not in existing_columns:
    cursor.execute(
        "ALTER TABLE interviews ADD COLUMN communication_score REAL"
    )

if "problem_solving_score" not in existing_columns:
    cursor.execute(
        "ALTER TABLE interviews ADD COLUMN problem_solving_score REAL"
    )

if "confidence_score" not in existing_columns:
    cursor.execute(
        "ALTER TABLE interviews ADD COLUMN confidence_score REAL"
    )

if "ats_score" not in existing_columns:
    cursor.execute(
        "ALTER TABLE interviews ADD COLUMN ats_score REAL"
    )

conn.commit()

# ----------------------------------
# Configure Page
# ----------------------------------
st.set_page_config(
    page_title="AI Mock Interview Platform",
    page_icon="🎯",
    layout="wide"
)

# ----------------------------------
# Initialize Groq Client
# ----------------------------------
client = Groq(
    api_key=os.getenv("GROQ_API_KEY")
)

# ----------------------------------
# Session State
# ----------------------------------
if "questions" not in st.session_state:
    st.session_state["questions"] = []

if "current_question" not in st.session_state:
    st.session_state["current_question"] = 0

if "answers" not in st.session_state:
    st.session_state["answers"] = []

if "interview_started" not in st.session_state:
    st.session_state["interview_started"] = False

if "evaluation_done" not in st.session_state:
    st.session_state["evaluation_done"] = False

if "last_feedback" not in st.session_state:
    st.session_state["last_feedback"] = ""
if "overall_report" not in st.session_state:
    st.session_state["overall_report"] = ""
if "learning_roadmap" not in st.session_state:
    st.session_state["learning_roadmap"] = ""

if "saved_to_db" not in st.session_state:
    st.session_state["saved_to_db"] = False

if "detected_skills" not in st.session_state:
    st.session_state["detected_skills"] = ""
if "weak_analysis" not in st.session_state:
    st.session_state["weak_analysis"] = ""

# ----------------------------------
# Sidebar
# ----------------------------------
st.sidebar.title("🎯 AI Interviewer")
st.sidebar.markdown("Practice for placements with AI-powered interviews.")
# ----------------------------------
# Main Header
# ----------------------------------
st.title("AI Mock Interview Platform")
st.header("Placement Preparation Platform")

# ----------------------------------
# Resume Upload
# ----------------------------------
uploaded_file = st.file_uploader(
    "Upload Resume (PDF)",
    type=["pdf"]
)

resume_text = ""

if uploaded_file is not None:
    try:
        pdf_reader = PdfReader(uploaded_file)

        for page in pdf_reader.pages:
            text = page.extract_text()

            if text:
                resume_text += text

        st.success("✅ Resume Uploaded Successfully")

        ats_prompt = f"""
Evaluate this resume for software engineering placements.

Resume:
{resume_text[:3000]}

Return EXACTLY:

ATS Score: X/100

Strengths:
- point

Weaknesses:
- point

Missing Keywords:
- point
"""

        try:
            ats_response = client.chat.completions.create(
                model="llama-3.1-8b-instant",
                messages=[{"role": "user", "content": ats_prompt}]
            )

            st.subheader("📄 ATS Resume Analysis")
            st.write(ats_response.choices[0].message.content)

        except Exception:
            pass

    except Exception as e:
        st.error(f"Error reading PDF: {e}")


# ----------------------------------
# Skills Extraction
# ----------------------------------
detected_skills = st.session_state["detected_skills"]

if resume_text and not st.session_state["detected_skills"]:
    try:
        skill_prompt = f"""
Extract ONLY technical skills from this resume.

Return ONLY a comma-separated list.

Do not add:
- headings
- explanations
- notes
- extra text

Resume:
{resume_text}
"""
        skill_response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "user",
                    "content": skill_prompt
                }
            ]
        )

        detected_skills = skill_response.choices[0].message.content
        st.session_state["detected_skills"] = detected_skills

    except Exception as e:
        st.error(f"Skill Extraction Error: {e}")

if st.session_state["detected_skills"]:
    st.success("Detected Skills")
    st.write(st.session_state["detected_skills"])

# ----------------------------------
# Skills Input
# ----------------------------------
skills = st.text_area(
    "Detected Skills (Edit if Needed)",
    value=detected_skills,
    height=120
)

# ----------------------------------
# Company Selection
# ----------------------------------
company = st.selectbox(
    "Select Company",
    [
        "Google",
        "Amazon",
        "Microsoft",
        "Adobe",
        "Flipkart",
        "Walmart",
        "Goldman Sachs",
        "JP Morgan",
        "Atlassian",
        "Uber"
    ]
)

# ----------------------------------
# Difficulty Selection
# ----------------------------------
level = st.selectbox(
    "Interview Difficulty",
    [
        "Easy",
        "Medium",
        "Hard"
    ]
)

# ----------------------------------
# DSA Topic Selection
# ----------------------------------
topic = st.selectbox(
    "Select DSA Topic",
    [
        "Arrays",
        "Binary Search",
        "Trees",
        "Graphs",
        "Dynamic Programming"
    ]
)

# ----------------------------------
# Generate Questions
# ----------------------------------
if st.button("Generate Interview Questions"):

    if not resume_text:
        st.warning("Please upload your resume first.")

    elif not skills.strip():
        st.warning("Please enter your skills.")

    else:

        prompt = f"""
Generate EXACTLY 5 interview questions.

Company: {company}
Difficulty: {level}
DSA Topic: {topic}

Resume:
{resume_text[:1500]}

Skills:
{skills[:500]}

Rules:
1. Question 1 must be from the resume projects.
2. Question 2 must be a deeper follow-up on the project.
3. Question 3 must be from the candidate skills.
4. Question 4 must be a coding question from {topic}.
5. Question 5 must match {company}'s interview style.
6. No HR questions.
7. Return only numbered questions.
"""

        try:
            with st.spinner("Generating Questions..."):
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {
                            "role": "user",
                            "content": prompt
                        }
                    ]
                )

                questions = response.choices[0].message.content

                question_list = []

                for line in questions.split("\n"):
                    line = line.strip()
                    if line and (
                        line.startswith("1.")
                        or line.startswith("2.")
                        or line.startswith("3.")
                        or line.startswith("4.")
                        or line.startswith("5.")
                    ):
                        question_list.append(line)

                st.session_state["questions"] = question_list
                st.session_state["current_question"] = 0
                st.session_state["answers"] = []
                st.session_state["interview_started"] = True
                st.session_state["evaluation_done"] = False
                st.session_state["last_feedback"] = ""
                st.session_state["overall_report"] = ""
                st.session_state["learning_roadmap"] = ""
                st.session_state["detected_skills"] = ""
                st.session_state["saved_to_db"] = False
                st.session_state["technical_score"] = "N/A"
                st.session_state["communication_score"] = "N/A"
                st.session_state["problem_solving_score"] = "N/A"
                st.session_state["weak_analysis"] = ""
                st.session_state["learning_roadmap"] = ""

            st.success(
                "Interview generated successfully. Start answering the questions below."
            )
        except Exception as e:
            if "rate_limit" in str(e).lower() or "429" in str(e):
                st.error(
                    "Groq daily token limit reached. Please wait for quota reset or use another API key."
                )
            else:
                st.error(f"Error: {e}")

# ----------------------------------
# Answer Evaluation
# ----------------------------------
st.markdown("---")
st.subheader("Answer Evaluation")

question = ""

if st.session_state["interview_started"]:

    current_idx = st.session_state["current_question"]

    if current_idx < len(st.session_state["questions"]):

        question = st.session_state["questions"][current_idx]

        st.subheader(
            f"Question {current_idx + 1} of {len(st.session_state['questions'])}"
        )

        st.info(question)
        progress = (current_idx + 1) / len(st.session_state["questions"])
        st.progress(progress)
        st.text_area(
            "Write Your Answer Here",
            key=f"answer_{current_idx}",
            height=250,
            placeholder="Type your answer here..."
        )

    else:

      st.success("🎉 Interview Completed")

if (
    st.session_state["interview_started"]
    and
    st.session_state["current_question"]
    >= len(st.session_state["questions"])
    and
    not st.session_state["overall_report"]
):

    all_answers = ""

    for item in st.session_state["answers"]:
        all_answers += f"""
Question:
{item['question']}

Answer:
{item['answer']}

Feedback:
{item['feedback']}

--------------------------------
"""

    report_prompt = f"""
You are a senior hiring manager.

Analyze ALL interview answers together.

Do NOT evaluate each question separately.

Provide ONLY one overall assessment for the complete interview.

{all_answers}

Generate report EXACTLY in this format:

Technical Score: X.X

Communication Score: X.X

Problem Solving Score: X.X

Strong Areas:
- point 1
- point 2

Weak Areas:
- point 1
- point 2

Topics To Improve:
- topic 1
- topic 2

Final Verdict:
Hire / Borderline / Reject

Rules:
1. Scores must be numeric.
2. Use exactly the labels:
   Technical Score:
   Communication Score:
   Problem Solving Score:
"""
    
    report = client.chat.completions.create(
        model="llama-3.1-8b-instant",
        messages=[
            {
                "role": "user",
                "content": report_prompt
            }
        ]
    )

    st.session_state["overall_report"] = (
        report.choices[0].message.content
    )

    report_text = st.session_state["overall_report"]

    technical_match = re.search(
        r"Technical Score:\s*([\d.]+)",
        report_text,
        re.IGNORECASE
    )

    communication_match = re.search(
        r"Communication Score:\s*([\d.]+)",
        report_text,
        re.IGNORECASE
    )

    problem_match = re.search(
        r"Problem Solving Score:\s*([\d.]+)",
        report_text,
        re.IGNORECASE
    )

    if technical_match:
        st.session_state["technical_score"] = technical_match.group(1)

    if communication_match:
        st.session_state["communication_score"] = communication_match.group(1)

    if problem_match:
        st.session_state["problem_solving_score"] = problem_match.group(1)

    weak_prompt = f"""
Based on this interview report:

{st.session_state['overall_report']}

Generate:

1. Strong Topics
2. Weak Topics
3. Recommended Revision Plan
4. Weekly Study Plan
5. Important DSA Topics
6. Important CS Subjects
"""

    try:
        weak_analysis = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "user",
                    "content": weak_prompt
                }
            ]
        )

        st.session_state["learning_roadmap"] = (
            weak_analysis.choices[0].message.content
        )

        weak_topic_prompt = f"""
Analyze the interview and identify:

1. Weak DSA Topics
2. Weak CS Subjects
3. Topic-wise score out of 10
4. Most Important Topic To Revise First

Report:

{st.session_state['overall_report']}
"""

        weak_topic_response = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[
                {
                    "role": "user",
                    "content": weak_topic_prompt
                }
            ]
        )

        st.session_state["weak_analysis"] = (
            weak_topic_response.choices[0].message.content
        )

    except Exception:
        st.session_state["learning_roadmap"] = (
            "Learning roadmap could not be generated because the Groq daily token limit was reached."
        )

# Initialize scores
if "technical_score" not in st.session_state:
    st.session_state["technical_score"] = "N/A"

if "communication_score" not in st.session_state:
    st.session_state["communication_score"] = "N/A"

if "problem_solving_score" not in st.session_state:
    st.session_state["problem_solving_score"] = "N/A"

# Show metrics only after report generation
if st.session_state["overall_report"]:

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric(
            "Technical Score",
            st.session_state["technical_score"]
        )

    with col2:
        st.metric(
            "Communication Score",
            st.session_state["communication_score"]
        )

    with col3:
        st.metric(
            "Problem Solving Score",
            st.session_state["problem_solving_score"]
        )

    st.subheader("📊 Final Interview Report")

    st.markdown(
        st.session_state["overall_report"]
    )

    st.download_button(
        "📥 Download Report",
        st.session_state["overall_report"],
        file_name="interview_report.txt",
        mime="text/plain"
    )

    try:
        avg_score = (
            float(st.session_state["technical_score"]) +
            float(st.session_state["communication_score"]) +
            float(st.session_state["problem_solving_score"])
        ) / 3

        st.progress(avg_score / 10)

        st.success(
            f"Overall Interview Score: {avg_score:.1f}/10"
        )
    except Exception:
        pass

    if st.session_state["learning_roadmap"]:
        st.subheader("📚 Learning Roadmap")
        st.write(st.session_state["learning_roadmap"])

if st.session_state["weak_analysis"]:

    st.subheader("📉 Weak Topic Analysis")
    st.write(st.session_state["weak_analysis"])

st.header("Interview Summary")

for idx, item in enumerate(st.session_state["answers"]):

    st.markdown(f"### Question {idx+1}")
    st.write(item["question"])

    st.write("**Your Answer:**")
    st.write(item["answer"])

    st.write("**Feedback:**")
    st.write(item["feedback"])

if (
    st.session_state["interview_started"]
    and
    st.session_state["current_question"]
    < len(st.session_state["questions"])
):
    answer = st.session_state.get(
        f"answer_{st.session_state['current_question']}",
        ""
    )
else:
    answer = ""

# ----------------------------------
# Evaluate Answer
# ----------------------------------
if st.button("Evaluate Answer"):

    if not question.strip():
        st.warning("Please select or paste an interview question.")

    elif not answer.strip():
        st.warning("Please write your answer.")

    elif len(answer.strip()) < 20:
        st.warning(
            "Answer too short. Please provide a detailed response."
        )
        st.stop()

    else:

        evaluation_prompt = f"""
You are a senior technical interviewer.

Interview Question:
{question}

Candidate Answer:
{answer}

IMPORTANT RULES:

1. Evaluate ONLY the candidate answer.
2. Never assume code or explanations that are not present.
3. If the answer is meaningless, random text, extremely short,
   or unrelated to the question, assign very low scores.
4. Do NOT invent code implementations.
5. Do NOT hallucinate technical explanations.

Return EXACTLY:

Technical Score: X.X
Communication Score: X.X
Problem Solving Score: X.X

Strong Areas:
...

Weak Areas:
...

Topics To Improve:
...

Final Verdict:
Hire / Borderline / Reject
"""

        try:

            with st.spinner("Evaluating Answer..."):

                evaluation = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {
                            "role": "user",
                            "content": evaluation_prompt
                        }
                    ]
                )

                feedback = evaluation.choices[0].message.content

                st.session_state["answers"].append(
                    {
                        "question": question,
                        "answer": answer,
                        "feedback": feedback
                    }
                )

                st.session_state["last_feedback"] = feedback
                st.session_state["evaluation_done"] = True

            st.rerun()

        except Exception as e:
            st.error(f"Error: {e}")

# ----------------------------------
# Show Feedback + Next Question
# ----------------------------------
if st.session_state["evaluation_done"]:

    st.subheader("AI Feedback")
    st.write(st.session_state["last_feedback"])

    if st.button("Next Question"):

        old_key = f"answer_{st.session_state['current_question']}"

        if old_key in st.session_state:
            del st.session_state[old_key]

        st.session_state["current_question"] += 1
        st.session_state["evaluation_done"] = False
        st.session_state["last_feedback"] = ""

        st.rerun()



# ----------------------------------
# Footer
# ----------------------------------
st.markdown("---")
st.caption(
    "Built using Streamlit + Groq LLM for Placement Preparation"
)


if (
    st.session_state["overall_report"]
    and not st.session_state["saved_to_db"]
):

    cursor.execute(
        """
        INSERT INTO interviews(
            company,
            technical_score,
            communication_score,
            problem_solving_score,
            score
        )
        VALUES(?,?,?,?,?)
        """,
        (
            company,
            float(st.session_state["technical_score"])
            if st.session_state["technical_score"] != "N/A"
            else None,
            float(st.session_state["communication_score"])
            if st.session_state["communication_score"] != "N/A"
            else None,
            float(st.session_state["problem_solving_score"])
            if st.session_state["problem_solving_score"] != "N/A"
            else None,
            st.session_state["overall_report"]
        )
    )

    conn.commit()
    st.session_state["saved_to_db"] = True

st.sidebar.subheader("Past Interviews")

history = cursor.execute(
"""
SELECT company,date
FROM interviews
ORDER BY id DESC
LIMIT 10
"""
).fetchall()

for item in history:
    st.sidebar.write(
        f"{item[0]} - {item[1]}"
    )
