"""
AI Chatbot for AttendAI
Uses Anthropic Claude API to answer attendance-related questions.
The chatbot gets a live snapshot of the database as context so it can
answer real questions like "Who has low attendance?" or "Can I miss class tomorrow?"
"""

import os
import json
from datetime import date, timedelta


def build_system_prompt(user, db, User, Course, Enrollment, Attendance):
    """
    Build a rich system prompt with live database context for the current user.
    This is what makes the chatbot actually useful — it knows real data.
    """
    today = date.today().strftime('%d %B %Y')
    role = user.role

    # ── Base personality ───────────────────────────────────────
    base = f"""You are AttendBot, the friendly AI assistant for AttendAI — an AI-powered Student Attendance Management System.
Today's date is {today}.
You are talking to: {user.username} (Role: {role.title()}, {'Roll No: ' + user.roll_no if user.roll_no else 'No roll number'}).

Your personality:
- Friendly, helpful, and encouraging
- Give specific answers based on the REAL DATA provided below
- Keep responses concise (2-4 sentences max unless a detailed breakdown is requested)
- Use emojis occasionally to be approachable 📊✅⚠️
- Never make up data — only use what's provided
- If asked something outside attendance/academics, politely redirect

IMPORTANT RULES:
- Always refer to the actual numbers from the data below
- Risk levels: SAFE ≥80%, CAUTION 75-79%, WARNING 65-74%, CRITICAL <65%
- Minimum required attendance is 75%
- For "can I miss class" questions, use the can_miss number from the data
"""

    # ── Role-specific context ──────────────────────────────────
    if role == 'student':
        context = _build_student_context(user, db, Course, Enrollment, Attendance)
    elif role == 'teacher':
        context = _build_teacher_context(user, db, Course, Enrollment, Attendance, User)
    else:  # admin
        context = _build_admin_context(db, User, Course, Enrollment, Attendance)

    return base + "\n\n" + context


def _build_student_context(user, db, Course, Enrollment, Attendance):
    """Build context for a student user."""
    enrollments = Enrollment.query.filter_by(student_id=user.id).all()
    courses_data = []

    for e in enrollments:
        course = Course.query.get(e.course_id)
        if not course:
            continue
        att_q = Attendance.query.filter_by(student_id=user.id, course_id=course.id)
        total = att_q.count()
        present = att_q.filter(Attendance.status.in_(['present', 'late'])).count()
        absent = total - present
        pct = round((present / total * 100), 1) if total > 0 else 0

        # Risk
        if pct >= 80: risk = 'SAFE'
        elif pct >= 75: risk = 'CAUTION'
        elif pct >= 65: risk = 'WARNING'
        else: risk = 'CRITICAL'

        # Can miss
        from math import floor, ceil
        max_abs = floor(present / 3) if present > 0 else 0
        can_miss = max(0, max_abs - absent)
        classes_needed = ceil(0.75 * total - present) + 1 if total > 0 and pct < 75 else 0

        # Recent 5 classes
        recent = att_q.order_by(Attendance.date.desc()).limit(5).all()
        recent_str = ', '.join([f"{r.date.strftime('%d %b')}:{r.status[0].upper()}" for r in recent])

        courses_data.append({
            'name': course.name,
            'code': course.code,
            'total': total,
            'present': present,
            'absent': absent,
            'pct': pct,
            'risk': risk,
            'can_miss': can_miss,
            'classes_needed': classes_needed,
            'recent': recent_str or 'No data yet'
        })

    overall_pct = round(sum(c['pct'] for c in courses_data) / len(courses_data), 1) if courses_data else 0

    lines = [f"=== STUDENT DATA FOR {user.username.upper()} ===",
             f"Overall Attendance: {overall_pct}%",
             f"Enrolled Courses: {len(courses_data)}", ""]

    for c in courses_data:
        lines.append(f"Course: {c['name']} ({c['code']})")
        lines.append(f"  Attendance: {c['pct']}% ({c['present']}/{c['total']} classes) — {c['risk']}")
        lines.append(f"  Can still miss: {c['can_miss']} classes" if c['pct'] >= 75
                     else f"  Need {c['classes_needed']} more classes to reach 75%")
        lines.append(f"  Recent: {c['recent']}")
        lines.append("")

    lines.append("=== SAMPLE QUESTIONS YOU CAN ANSWER ===")
    lines.append("- What is my attendance in [course]?")
    lines.append("- Can I miss tomorrow's class?")
    lines.append("- Which course am I doing worst in?")
    lines.append("- How many classes do I need to attend to be safe?")
    lines.append("- What is my risk level?")

    return '\n'.join(lines)


def _build_teacher_context(user, db, Course, Enrollment, Attendance, User):
    """Build context for a teacher user."""
    courses = Course.query.filter_by(teacher_id=user.id).all()
    lines = [f"=== TEACHER DATA FOR {user.username.upper()} ===",
             f"Assigned Courses: {len(courses)}", ""]

    total_at_risk = 0

    for course in courses:
        enrolled_ids = [e.student_id for e in Enrollment.query.filter_by(course_id=course.id).all()]
        students = User.query.filter(User.id.in_(enrolled_ids)).all()

        risk_counts = {'SAFE': 0, 'CAUTION': 0, 'WARNING': 0, 'CRITICAL': 0}
        at_risk_names = []
        pcts = []

        for s in students:
            att_q = Attendance.query.filter_by(student_id=s.id, course_id=course.id)
            total = att_q.count()
            present = att_q.filter(Attendance.status.in_(['present', 'late'])).count()
            pct = round((present / total * 100), 1) if total > 0 else 0
            pcts.append(pct)

            if pct >= 80: risk = 'SAFE'
            elif pct >= 75: risk = 'CAUTION'
            elif pct >= 65: risk = 'WARNING'
            else: risk = 'CRITICAL'
            risk_counts[risk] += 1

            if pct < 75:
                at_risk_names.append(f"{s.username}({pct}%)")
                total_at_risk += 1

        avg = round(sum(pcts) / len(pcts), 1) if pcts else 0
        total_classes = len(set(
            r.date for r in Attendance.query.filter_by(course_id=course.id).all()
        ))

        lines.append(f"Course: {course.name} ({course.code})")
        lines.append(f"  Students: {len(students)} enrolled, {total_classes} classes held")
        lines.append(f"  Average Attendance: {avg}%")
        lines.append(f"  Risk: SAFE={risk_counts['SAFE']} CAUTION={risk_counts['CAUTION']} "
                     f"WARNING={risk_counts['WARNING']} CRITICAL={risk_counts['CRITICAL']}")
        if at_risk_names:
            lines.append(f"  At-risk students (<75%): {', '.join(at_risk_names[:10])}")
        lines.append("")

    lines.append("=== SAMPLE QUESTIONS YOU CAN ANSWER ===")
    lines.append("- Which students are at risk in [course]?")
    lines.append("- Who has the lowest attendance?")
    lines.append("- What is the average attendance for [course]?")
    lines.append("- How many students need parent alerts?")
    lines.append("- Who was absent most this week?")

    return '\n'.join(lines)


def _build_admin_context(db, User, Course, Enrollment, Attendance):
    """Build context for an admin user."""
    students = User.query.filter_by(role='student').all()
    teachers = User.query.filter_by(role='teacher').all()
    courses = Course.query.all()

    risk_counts = {'SAFE': 0, 'CAUTION': 0, 'WARNING': 0, 'CRITICAL': 0}
    pcts = []
    for s in students:
        att_q = Attendance.query.filter_by(student_id=s.id)
        total = att_q.count()
        present = att_q.filter(Attendance.status.in_(['present', 'late'])).count()
        pct = round((present / total * 100), 1) if total > 0 else 0
        pcts.append(pct)
        if pct >= 80: risk_counts['SAFE'] += 1
        elif pct >= 75: risk_counts['CAUTION'] += 1
        elif pct >= 65: risk_counts['WARNING'] += 1
        else: risk_counts['CRITICAL'] += 1

    overall_avg = round(sum(pcts) / len(pcts), 1) if pcts else 0
    total_att = Attendance.query.count()

    lines = [
        "=== SYSTEM-WIDE ADMIN DATA ===",
        f"Total Students: {len(students)}",
        f"Total Teachers: {len(teachers)}",
        f"Total Courses: {len(courses)}",
        f"Total Attendance Records: {total_att}",
        f"Overall Average Attendance: {overall_avg}%",
        f"Risk Distribution: SAFE={risk_counts['SAFE']} CAUTION={risk_counts['CAUTION']} "
        f"WARNING={risk_counts['WARNING']} CRITICAL={risk_counts['CRITICAL']}",
        "",
        "=== SAMPLE QUESTIONS YOU CAN ANSWER ===",
        "- What is the overall attendance this month?",
        "- How many students are at critical risk?",
        "- Which course has the lowest attendance?",
        "- How many parent alerts should be sent today?",
    ]
    return '\n'.join(lines)


def get_chatbot_response(user_message, conversation_history, system_prompt):
    """
    Call the Anthropic API and return the assistant's response.
    Returns (response_text, error_message)
    """
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=os.environ.get('ANTHROPIC_API_KEY'))

        # Build messages array (keep last 10 turns for context)
        messages = conversation_history[-10:] + [
            {"role": "user", "content": user_message}
        ]

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            system=system_prompt,
            messages=messages
        )

        return response.content[0].text, None

    except ImportError:
        return None, "Anthropic library not installed. Run: pip install anthropic"
    except Exception as e:
        err = str(e)
        if 'api_key' in err.lower() or 'authentication' in err.lower():
            return None, "Invalid API key. Please set ANTHROPIC_API_KEY in your .env file."
        return None, f"API error: {err}"


# ── Quick-reply suggestions per role ──────────────────────────
QUICK_REPLIES = {
    'student': [
        "What's my overall attendance?",
        "Can I miss class tomorrow?",
        "Which course am I at risk in?",
        "How many classes do I need to attend?",
        "What's my risk level?",
    ],
    'teacher': [
        "Who has low attendance in my courses?",
        "Which students need parent alerts?",
        "What's the average attendance this week?",
        "Who was absent most recently?",
        "Show me at-risk students",
    ],
    'admin': [
        "What's the overall attendance today?",
        "How many students are at critical risk?",
        "Which course has lowest attendance?",
        "How many alerts should be sent?",
        "Give me a system summary",
    ]
}
