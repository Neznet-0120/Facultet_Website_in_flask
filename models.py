from flask_sqlalchemy import SQLAlchemy
from datetime import datetime


db = SQLAlchemy()


teacher_subjects = db.Table(
    'teacher_subjects',
    db.Column('teacher_id', db.Integer, db.ForeignKey('users.id'), primary_key=True),
    db.Column('subject_id', db.Integer, db.ForeignKey('subjects.id'), primary_key=True)
)

class Group(db.Model):
    __tablename__ = "groups"
    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(100), unique = True, nullable = False)
    course = db.Column(db.Integer, nullable = False)
    students = db.relationship('User', back_populates = 'group', lazy = 'dynamic')
    schedules = db.relationship('Schedule', back_populates = 'group', lazy = 'dynamic')
    __table_args__ = (db.UniqueConstraint('name', 'course', name='uq_group_name_course'),)

    def __repr__(self):
        return f"<Group {self.name}>"    

class Subject(db.Model):
    __tablename__ = "subjects"
    id = db.Column(db.Integer, primary_key = True)
    name = db.Column(db.String(120), unique = True, nullable = False)
    teachers = db.relationship('User', secondary = teacher_subjects, back_populates = "subjects")

    def __repr__(self):
        return f"<Subject {self.name}>"


class User(db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key = True)
    role = db.Column(db.String(20), nullable=False, default="student", 
                 server_default="student", 
                 comment="student, teacher, admin")
    username = db.Column(db.String(50), unique = True, nullable = False)
    email = db.Column(db.String(120), unique = True, nullable = False)
    password_hash = db.Column(db.String(255), nullable = False)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable = True)
    group = db.relationship("Group", back_populates = "students")
    course = db.Column(db.Integer, nullable = True)
    subjects = db.relationship('Subject', secondary = teacher_subjects, back_populates = "teachers")
    status = db.Column(db.String(20), nullable = False, default = "pending")
    profile_image = db.Column(db.String(255), nullable=True, default="default.png")
    created_at = db.Column(db.DateTime, default = datetime.utcnow)

    def __repr__(self):
        return f"<User {self.username}>"
    

class Schedule(db.Model):
    __tablename__ = "schedules"
    id = db.Column(db.Integer, primary_key = True)
    group_id = db.Column(db.Integer, db.ForeignKey("groups.id"), nullable = False)
    subject_id = db.Column(db.Integer, db.ForeignKey("subjects.id"), nullable = False)
    teacher_id = db.Column(db.Integer, db.ForeignKey("users.id"))
    course = db.Column(db.Integer, nullable = False)
    weekday = db.Column(db.Integer, nullable = False)
    start_time = db.Column(db.Time, nullable = False)
    end_time = db.Column(db.Time, nullable = False)
    created_at = db.Column(db.DateTime, default = datetime.utcnow)

    group = db.relationship("Group", back_populates = "schedules")
    subject = db.relationship("Subject")
    teacher = db.relationship("User")
    
    __table_args__ = (
    db.CheckConstraint('weekday >= 0 AND weekday <= 6', name='ck_weekday'),
    db.UniqueConstraint('group_id', 'course', 'weekday', 'start_time', name='uq_schedule_time'),
)

    def __repr__(self):
        return f"<Schedule group={self.group_id}, course = {self.course} ,subject={self.subject_id}, weekday={self.weekday}>"


news_likes = db.Table(
    "news_likes",
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("news_id", db.Integer, db.ForeignKey("news.id", ondelete = "CASCADE"), primary_key=True)
)


class Comments(db.Model):
    __tablename__ = "comments"
    id = db.Column(db.Integer, primary_key = True)
    content = db.Column(db.Text, nullable = False)
    created_at = db.Column(db.DateTime, default = datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable = False)
    news_id = db.Column(db.Integer, db.ForeignKey("news.id", ondelete = "CASCADE"), nullable = False)

    author = db.relationship("User", backref = "comments")
    

class News(db.Model):
    __tablename__ = "news"
    id = db.Column(db.Integer, primary_key = True)
    title = db.Column(db.String(255), nullable = False)
    content = db.Column(db.Text, nullable = False)
    created_at = db.Column(db.DateTime, default = datetime.utcnow)
    author_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable = False)


    author = db.relationship("User")
    likes = db.relationship("User", secondary=news_likes, backref="liked_news")
    comments = db.relationship(
        "Comments",
        backref="news",
        cascade="all, delete-orphan",
        lazy=True
    )

    def __repr__(self):
        return f"<News {self.title}>"




    

