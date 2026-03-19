"""
Initialize database and create admin user.
Run: python create_admin.py
Run with sample data: python create_admin.py --seed
"""
import sys
import os
from dotenv import load_dotenv
load_dotenv()

def create_admin():
    from app import create_app, db
    from app.models import User, Course, Enrollment, Attendance

    env = os.environ.get('FLASK_ENV', 'development')
    app = create_app('production' if env == 'production' else 'development')

    with app.app_context():
        db.create_all()
        print("✅ Database tables created")

        if not User.query.filter_by(username='admin').first():
            admin = User(username='admin', email='admin@college.edu',
                        role='admin', is_active=True)
            admin.set_password('admin123')
            db.session.add(admin)
            db.session.commit()
            print("✅ Admin created: username=admin, password=admin123")
        else:
            print("ℹ️  Admin already exists")

        if '--seed' in sys.argv:
            seed_sample_data(db, User, Course, Enrollment, Attendance)


def seed_sample_data(db, User, Course, Enrollment, Attendance):
    import random
    from datetime import date, timedelta

    print("\n🌱 Seeding sample data...")

    teachers = []
    for i in range(1, 4):
        u = User.query.filter_by(username=f'teacher{i}').first()
        if not u:
            u = User(username=f'teacher{i}', email=f'teacher{i}@college.edu',
                     role='teacher', is_active=True)
            u.set_password('teacher123')
            db.session.add(u)
        teachers.append(u)
    db.session.flush()

    course_data = [
        ('Data Structures', 'CS301', 0),
        ('Database Systems', 'CS302', 0),
        ('Web Technologies', 'CS303', 1),
        ('Computer Networks', 'CS304', 1),
        ('Operating Systems', 'CS305', 2),
    ]
    courses = []
    for name, code, t_idx in course_data:
        c = Course.query.filter_by(code=code).first()
        if not c:
            c = Course(name=name, code=code, teacher_id=teachers[t_idx].id)
            db.session.add(c)
        courses.append(c)
    db.session.flush()

    students = []
    for i in range(1, 21):
        u = User.query.filter_by(username=f'student{i}').first()
        if not u:
            u = User(
                username=f'student{i}', email=f'student{i}@college.edu',
                role='student', is_active=True,
                roll_no=f'CS{100+i}',
                parent_phone=f'+9198765{43200+i:05d}',
                parent_email=f'parent{i}@example.com'
            )
            u.set_password('student123')
            db.session.add(u)
        students.append(u)
    db.session.flush()

    for s in students:
        for c in courses:
            if not Enrollment.query.filter_by(student_id=s.id, course_id=c.id).first():
                db.session.add(Enrollment(student_id=s.id, course_id=c.id))
    db.session.flush()

    today = date.today()
    patterns = {'good': 0.92, 'average': 0.80, 'low': 0.70, 'critical': 0.55}
    pattern_list = ['good']*6 + ['average']*8 + ['low']*4 + ['critical']*2

    for day_offset in range(30, 0, -1):
        att_date = today - timedelta(days=day_offset)
        if att_date.weekday() >= 5:
            continue
        for c in courses:
            for i, s in enumerate(students):
                prob = patterns[pattern_list[i]]
                r = random.random()
                status = 'present' if r < prob else ('late' if r < prob + 0.05 else 'absent')
                if not Attendance.query.filter_by(student_id=s.id, course_id=c.id, date=att_date).first():
                    db.session.add(Attendance(student_id=s.id, course_id=c.id,
                                              date=att_date, status=status))

    db.session.commit()
    print("✅ Sample data seeded — 20 students, 5 courses, 30 days attendance")
    print("\nDemo accounts:")
    print("  Admin:   admin / admin123")
    print("  Teacher: teacher1 / teacher123")
    print("  Student: student1 / student123")


if __name__ == '__main__':
    create_admin()
