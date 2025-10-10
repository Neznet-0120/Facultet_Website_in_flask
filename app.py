from flask import Flask, redirect, render_template, url_for, request, session, flash
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import os
from models import db, Group, Subject, User, Schedule, News, Comments
from utils.auth import login_required, admin_required

app = Flask(__name__)
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///iqr.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.secret_key = "aiwprton"
db.init_app(app)
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "static/uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


@app.route("/register", methods = ["POST", "GET"])
def register():
    groups = Group.query.order_by(Group.name).all()
    if request.method == "POST":
        username = request.form["username"]
        email = request.form["email"]
        password = request.form["password"]
        role = request.form["role"]
        status = "pending"

        if not username or not email or not password or not role:
            flash("Все поля обязательны для запольнения !")
            return render_template("register.html", groups = groups, username = username, email = email, role = role)
        
        if User.query.filter_by(username = username).first():
            flash("Это имя пользователя уже занято!")
            return redirect(url_for("register", groups = groups, username = username, email = email, role = role))
        
        if User.query.filter_by(email = email).first():
            flash("Этот email уже зарегистрирован!")
            return redirect(url_for("register", groups = groups, username = username, email = email, role = role))

        if len(password) >= 8:
            password_hash = generate_password_hash(password)
        else:
            flash("Пароль должен быть не короче 8 символов!")
            return render_template("register.html", groups = groups, username = username, email = email, role = role)
        
        
        group_id = request.form['group_id'] if role == "student" else None
        course = request.form['course'] if role == "student" else None
        user = User(username = username, email = email, password_hash = password_hash, role = role, group_id = group_id, course = course, status = status)
        
        try:
            db.session.add(user)
            db.session.commit()
            flash("Запрос на регистрции успешно отправлен.")
            return redirect(url_for("index"))
        except Exception as e:
            flash(f"Ошибка при регистрации: {str(e)}.")
            return render_template("register.html", groups = groups, username = username, email = email, role = role)
    
    return render_template("register.html", groups = groups)


@app.route("/login", methods=["POST", "GET"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")
        form_role = request.form.get("role")

        user = User.query.filter_by(email=email).first()

        # 1. Проверка существования пользователя
        if not user:
            flash("Пользователь не найден.", "error")
            return redirect(url_for("login"))

        # 2. Проверка роли
        if user.role != form_role:
            flash("Вы выбрали неправильную роль.", "error")
            return redirect(url_for("login"))

        # 3. Проверка статуса
        if user.status == "pending":
            flash("Ваш запрос ещё не одобрен. Подождите подтверждения.", "warning")
            return redirect(url_for("login"))
        elif user.status == "rejected":
            flash("Ваш запрос был отклонён. Попробуйте зарегистрироваться снова.", "error")
            return redirect(url_for("register"))

        # 4. Проверка пароля
        if not check_password_hash(user.password_hash, password):
            flash("Неверный пароль!", "error")
            return redirect(url_for("login"))

        # 5. Авторизация успешна → сохраняем данные в сессии
        session["user_id"] = user.id
        session["role"] = user.role
        flash("Добро пожаловать!", "success")

        # === 6. Разное перенаправление в зависимости от роли ===
        if user.role == "admin":
            return redirect(url_for("admin"))  # твой маршрут для админ-панели
        else:
            return redirect(url_for("profile"))  # обычная главная страница

    # Если GET-запрос → показываем страницу логина
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("Выход успешно выполнен !")
    return redirect(url_for("login"))


@app.route("/")
def index():
    user = None
    if "user_id" in session:
        user = User.query.get(session["user_id"])
    news = News.query.order_by(News.created_at.desc()).all()
    return render_template("index.html", news=news, user=user)


@app.route("/profile")
@login_required
def profile():
    user = User.query.get(session["user_id"])
    group = None
    schedule = None

    # Получаем все посты пользователя
    news = News.query.filter_by(author_id=user.id).order_by(News.created_at.desc()).all()

    # Если студент — показываем расписание его группы
    if user.role == "student":
        group = Group.query.get(user.group_id)
        schedule = (
            Schedule.query
            .filter_by(group_id=user.group_id, course=user.course)
            .order_by(Schedule.weekday, Schedule.start_time)
            .all()
        )

    # Если преподаватель — показываем расписание по его id
    elif user.role == "teacher":
        schedule = (
            Schedule.query
            .filter_by(teacher_id=user.id)
            .order_by(Schedule.weekday, Schedule.start_time)
            .all()
        )

    # Для админа можно показать все расписания или ничего — решим позже
    return render_template("profile.html", user=user, group=group, schedule=schedule, news=news)


@app.route("/profile/photo", methods=["POST"])
@login_required
def upload_or_edit_photo():
    """Загрузка нового фото профиля или редактирование существующего"""
    if "photo" not in request.files:
        flash("Файл не выбран!", "error")
        return redirect(url_for("profile"))

    file = request.files["photo"]
    if file.filename == "":
        flash("Файл не выбран!", "error")
        return redirect(url_for("profile"))

    if not allowed_file(file.filename):
        flash("Неверный формат файла! Допустимо: png, jpg, jpeg, gif.", "error")
        return redirect(url_for("profile"))

    user = User.query.get(session["user_id"])

    # Удаляем старое фото, если оно есть
    if user.profile_image:
        old_path = os.path.join(app.config["UPLOAD_FOLDER"], user.profile_image)
        if os.path.exists(old_path):
            try:
                os.remove(old_path)
            except Exception as e:
                flash(f"Не удалось удалить старое фото: {str(e)}", "error")

    # Сохраняем новое фото
    filename = f"user_{user.id}_{file.filename}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
    file.save(filepath)

    user.profile_image = filename
    db.session.commit()
    flash("Фото профиля успешно загружено!", "success")

    return redirect(url_for("profile"))

@app.route("/profile/photo/delete")
@login_required
def delete_photo():
    """Удаление фото профиля"""
    user = User.query.get(session["user_id"])
    if user.profile_image:
        try:
            path = os.path.join(app.config["UPLOAD_FOLDER"], user.profile_image)
            if os.path.exists(path):
                os.remove(path)
            user.profile_image = None
            db.session.commit()
            flash("Фото профиля удалено!", "success")
        except Exception as e:
            flash(f"Ошибка при удалении фото: {str(e)}", "error")
    else:
        flash("Фото профиля отсутствует.", "info")

    return redirect(url_for("profile"))


@app.route("/admin")
@admin_required
def admin():
    current_user = User.query.get(session["user_id"])

    # Статистика
    users_count = User.query.count()
    groups_count = Group.query.count()
    subjects_count = Subject.query.count()
    news_count = News.query.count()

    # Ожидающие пользователи (ждут подтверждения)
    pending_users = User.query.filter_by(status="pending").all()

    # Последние новости
    latest_news = News.query.order_by(News.created_at.desc()).limit(5).all()

    return render_template(
        "admin.html",
        user=current_user,
        users_count=users_count,
        groups_count=groups_count,
        subjects_count=subjects_count,
        news_count=news_count,
        pending_users=pending_users,
        latest_news=latest_news
    )
    

@app.route("/admin/update_status", methods = ["POST"])
@admin_required
def admin_update_status():
    user_id = request.form.get("user_id")
    action = request.form.get("action")
    user = User.query.get(user_id)
    if not user:
        flash("Пользователь не найден.")
        return redirect(url_for("admin"))
    
    try:
        if action == "approve":
            user.status = "approved"
            db.session.commit()
            flash("Пользователь успешно одобрен.")
        elif action == "reject":
            user.status = "rejected"
            db.session.commit()
            flash("Пользователь успешно отклонён.")
        else:
            flash("Некорректное действие!", "error")
            return redirect(url_for("admin"))

    except Exception as e: 
        db.session.rollback()
        flash(f"Ошибка при обновлении: {str(e)}", "error")

    return redirect(url_for("admin"))   


@app.route("/admin/schedule", methods = ["POST", "GET"])
@admin_required
def admin_schedule():
    if request.method == "POST":
        try:
            group_id = int(request.form.get("group_id"))
            course = int(request.form.get("course"))
            subject_id = int(request.form.get("subject_id"))
            teacher_id = int(request.form.get("teacher_id"))
            weekday = int(request.form.get("weekday"))

            if course not in (1, 2, 3, 4):
                flash("Курс должен быть 1, 2, 3 или 4.", "error")
                return redirect(url_for("admin_schedule"))

            start_time = datetime.strptime(request.form.get("start_time"), "%H:%M").time()
            end_time = datetime.strptime(request.form.get("end_time"), "%H:%M").time()
            
            if start_time >= end_time:
                flash("Время начала должно быть раньше времени окончания.", "error")
                return redirect(url_for("admin_schedule"))
            
            group_conflict = Schedule.query.filter(
                Schedule.group_id == group_id,
                Schedule.course == course,
                Schedule.weekday == weekday,
                Schedule.start_time < end_time,
                Schedule.end_time > start_time
            ).first()

            if group_conflict:
                flash("Конфликт у этой группы/курса уже есть пара в это время.", "error")
                return redirect(url_for("admin_schedule"))
            
            teacher_conflict = Schedule.query.filter(
                Schedule.teacher_id == teacher_id,
                Schedule.weekday == weekday,
                Schedule.start_time < end_time,
                Schedule.end_time > start_time,
            ).first()

            if teacher_conflict:
                flash("Конфликт: у преподователя уже есть пара в это время.","error")
                return redirect(url_for("admin_schedule"))
            
            schedule = Schedule(
                group_id = group_id,
                subject_id = subject_id,
                teacher_id = teacher_id,
                course = course,
                weekday = weekday,
                start_time = start_time,
                end_time = end_time
            )
            db.session.add(schedule)
            db.session.commit()
            flash("Расписание успешно добавлено !", "success")
        
        except ValueError:
            db.session.rollback()
            flash("Некорректные данные формы (числовые поля или формат времени).", "error")
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при добавлениии расписания: {str(e)}", "error")

        return redirect(url_for("admin_schedule"))

    groups = Group.query.all()
    subjects = Subject.query.all()
    teachers = User.query.filter_by(role = "teacher").all()
    schedules = Schedule.query.order_by(Schedule.weekday, Schedule.start_time).all()

    return render_template(
        "admin_schedule.html",
        groups = groups,
        subjects = subjects,
        teachers = teachers,
        schedules = schedules
    )


@app.route("/admin/schedule/delete/<id>")
@admin_required
def delete_schedule(id):
    schedule = Schedule.query.get(id)
    if schedule:
        db.session.delete(schedule)
        db.session.commit()
        flash("Пара удалена!")
    else:
        flash("Ошибка. Повторите попытку заново!")
    
    return redirect(url_for("admin_schedule"))
    

@app.route("/admin/edit_schedule/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_schedule(id):
    schedule = Schedule.query.get_or_404(id)  # <-- ищем по id или 404 если нет
    
    groups = Group.query.all()
    subjects = Subject.query.all()
    teachers = User.query.filter_by(role="teacher").all()

    if request.method == "POST":
        try:
            schedule.group_id = int(request.form.get("group_id"))
            schedule.course = int(request.form.get("course"))
            schedule.subject_id = int(request.form.get("subject_id"))
            schedule.teacher_id = int(request.form.get("teacher_id"))
            schedule.weekday = int(request.form.get("weekday"))

            start_time = datetime.strptime(request.form.get("start_time"), "%H:%M").time()
            end_time = datetime.strptime(request.form.get("end_time"), "%H:%M").time()

            if start_time >= end_time:
                flash("Время начала должно быть раньше времени окончания.", "error")
                return redirect(url_for("edit_schedule", id=id))

            schedule.start_time = start_time
            schedule.end_time = end_time

            db.session.commit()
            flash("Расписание успешно обновлено!", "success")
            return redirect(url_for("admin_schedule"))

        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при обновлении расписания: {str(e)}", "error")
            return redirect(url_for("edit_schedule", id=id))

    return render_template(
        "edit_schedule.html",
        schedule=schedule,
        groups=groups,
        subjects=subjects,
        teachers=teachers
    )


@app.route("/admin/groups", methods = ["POST", "GET"])
@admin_required
def admin_groups():
    if request.method == "POST":
        name = request.form.get("name")
        course = request.form.get("course")

        if not name or not course:
            flash("Заполните все поля!", "danger")
            return redirect(url_for("admin_groups"))
        
        try:
            group = Group(name = name, course = int(course))
            db.session.add(group)
            db.session.commit()
            flash("Группа успешно добавлена!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при добавлении группы: {str(e)}", "danger")
        
        return redirect(url_for("admin_groups"))
    
    groups = Group.query.all()
    return render_template("admin_groups.html", groups = groups)


@app.route("/admin/edit_group/<int:id>", methods=["GET", "POST"])
@admin_required
def edit_group(id):
    group = Group.query.get_or_404(id)

    if request.method == "POST":
        group.name = request.form.get("name")
        group.course = request.form.get("course")
        try:
            db.session.commit()
            flash("Группа успешно обновлена!", "success")
            return redirect(url_for("admin_groups"))
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при обновлении группы: {str(e)}", "error")

    return render_template("edit_group.html", group=group)


@app.route("/admin/groups/delete/<int:id>", methods=["POST", "GET"])
@admin_required
def delete_group(id):
    group = Group.query.get_or_404(id)
    try:
        db.session.delete(group)
        db.session.commit()
        flash("Группа успешно удалена!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении группы: {str(e)}", "error")
    return redirect(url_for("admin_groups"))


@app.route("/admin/subjects", methods = ["POST", "GET"])
@admin_required
def admin_subjects():
    teachers = User.query.filter_by(role = "teacher").all()
    subjects = Subject.query.all()

    if request.method == "POST":
        name = request.form.get("name")
        teacher_ids = request.form.getlist("teachers")

        if not name:
            flash("Введите название предмета", "error")
            return redirect(url_for("admin_subjects"))

        try:
            subject = Subject(name = name)
            selected_teachers = User.query.filter(User.id.in_(teacher_ids)).all()
            subject.teachers = selected_teachers

            db.session.add(subject)
            db.session.commit()
            flash("Предмет успешно добавлен.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Произошло ошибка при добавлении {str(e)}.")

        return redirect(url_for("admin_subjects"))
    
    return render_template("admin_subjects.html", teachers = teachers, subjects = subjects)


@app.route("/admin/subjects/delete/<int:id>", methods = ["POST"])
@admin_required
def subject_delete(id):
    subject = Subject.query.get(id)
    if subject:
        db.session.delete(subject)
        db.session.commit()
        flash("Предмет успешно удален")
    else:    
        flash("Предмет не существует")
    
    return redirect(url_for("admin_subjects"))


@app.route("/admin/subjects/edit/<int:id>", methods = ["POST", "GET"])
@admin_required
def edit_subjects(id):
    subject = Subject.query.get(id)
    if not subject:
        flash("Предмет не найден", "error")
        return redirect(url_for("admin_subjects"))
    
    teachers = User.query.filter_by(role = "teacher").all()

    if request.method == "POST":
        name = request.form.get("name")
        teacher_ids = request.form.getlist("teachers")

        if not name:
            flash("Название предмета не может быт пустым", "error")
            return redirect(url_for("admin_subjects"))

        try:
            subject.name = name
            selected_teachers = User.query.filter(User.id.in_(teacher_ids)).all()
            subject.teachers = selected_teachers

            db.session.commit()
            flash("Изменение успешно принят.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Произошло ошибка при добавление изменении {str(e)}.")

        return redirect(url_for("admin_subjects"))
    
    return render_template("edit_subjects.html", subject = subject ,teachers = teachers)


@app.route("/news/add", methods = ["POST", "GET"])
@login_required
def add_news():
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")

        if not title or not content:
            flash("Все поля обязательны для заполнение.")
            return redirect(url_for("add_news"))
        
        news = News(title = title, content = content, author_id = session["user_id"])
        try:
            db.session.add(news)
            db.session.commit()
            flash("Пост успешно добавлен.", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Произошла ошибка при добавлении {str(e)}")
        
        return redirect(url_for("news_detail", id = news.id))
    
    return render_template("add_news.html")


@app.route("/news/like/<int:id>")
@login_required
def like_news(id):
    news_items = News.query.get_or_404(id)
    user = User.query.get(session["user_id"])

    if user in news_items.likes:
        news_items.likes.remove(user)
        flash("Лайк снят!", "success")
    else:
        news_items.likes.append(user)
        flash("Лайк поставлен!", "success")
    
    db.session.commit()
    return redirect(url_for("news_detail", id = id))


@app.route("/news/comment/<int:id>", methods=["POST"])
@login_required
def comment_news(id):
    news_item = News.query.get_or_404(id)
    content = request.form.get("content")

    if not content:
        flash("Комментарий не может быть пустым!", "error")
        return redirect(url_for("news_detail", id = id))

    comment = Comments(content=content, author_id=session["user_id"], news_id=id)
    db.session.add(comment)
    db.session.commit()
    flash("Комментарий добавлен!", "success")
    return redirect(url_for("news_detail", id = id))


@app.route("/news/<int:id>")
@login_required
def news_detail(id):
    # Получаем новость по ID
    news_item = News.query.get_or_404(id)
    
    # Получаем комментарии к новости (сортировка по дате, новые первыми)
    comments = Comments.query.filter_by(news_id=id).order_by(Comments.created_at.desc()).all()
    
    # Список ID пользователей, которые лайкнули эту новость
    liked_user_ids = [user.id for user in news_item.likes]

    return render_template(
        "news_detail.html",
        news=news_item,
        comments=comments,
        liked_user_ids=liked_user_ids
    )


@app.route("/news/edit/<int:id>", methods = ["POST", "GET"])
@login_required
def edit_news(id):
    news_item = News.query.get_or_404(id)
    current_user = User.query.get(session["user_id"])
    if current_user.id != news_item.author_id and current_user.role != "admin":
        flash("У вас нет прав на редактирование этого поста!", "error")
        return redirect(url_for("index"))
    if request.method == "POST":
        title = request.form.get("title")
        content = request.form.get("content")
        if not title or not content:
            flash("Все поля обязательны для заполнения!", "error")
            return render_template("edit_news.html", id = id)
        news_item.title = title
        news_item.content = content
        try:
            db.session.commit()
            flash("Пост успешно обновлён!", "success")
        except Exception as e:
            db.session.rollback()
            flash(f"Ошибка при обновлении поста: {str(e)}.", "error")
        return redirect(url_for("news_detail", id = id))
    return render_template("edit_news.html", news = news_item)


@app.route("/news/delete/<int:id>")
@login_required
def delete_news(id):
    news_item = News.query.get_or_404(id)
    current_user = User.query.get(session["user_id"])
    if current_user.id != news_item.author_id and current_user.role != "admin":
        flash("У вас нет прав на редактирование этого поста!", "error")
        return redirect(url_for("news_detail", id = id))
    try:
        db.session.delete(news_item)
        db.session.commit()
        flash("Пост успешно удален!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Произошла ошибка при удалении {str(e)}.", "error")

    return redirect(url_for("index"))


@app.route("/comment/delete/<int:id>")
@login_required
def delete_comment(id):
    comment = Comments.query.get_or_404(id)
    current_user = User.query.get(session["user_id"])
    if (current_user.role != "admin"
        and current_user.id != comment.author_id 
        and current_user.id != comment.news.author_id):
        flash("У вас нет прав на удаление этого комментария!", "error")
        return redirect(url_for("news_detail", id = comment.news_id))
    try:
        db.session.delete(comment)
        db.session.commit()
        flash("Комментарий успешно удалён!", "success")
    except Exception as e:
        db.session.rollback()
        flash(f"Произошла ошибка при удалении комментария: {str(e)}.")
    return redirect(url_for("news_detail", id = comment.news_id))


@app.route("/profile/delete/confirm")
@login_required
def confirm_delete_profile():
    user = User.query.get(session["user_id"])
    return render_template("delete_profile.html", user=user)


@app.route("/profile/delete", methods = ["POST"])
@login_required
def delete_profile():
    current_user = User.query.get(session["user_id"])
    password = request.form.get("password")

    if not password:
        flash("Введите пароль !", "error")
        return redirect(url_for("profile"))

    if not check_password_hash(current_user.password_hash, password):
        flash("Неверный пароль", "error") 
        return redirect(url_for("confirm_delete_profile"))
    
    try:
        news_items = News.query.filter_by(author_id = current_user.id).all()
        for item in news_items:
            db.session.delete(item)
        if current_user.profile_image:
            try:
                os.remove(os.path.join(app.config["UPLOAD_FOLDER"], current_user.profile_image))
            except FileNotFoundError:
                pass
        
        db.session.delete(current_user)
        db.session.commit()
        session.clear()

        flash("Профиль и связанные данные успешно удалены!","success")
        return redirect(url_for("register"))
    
    except Exception as e:
        db.session.rollback()
        flash(f"Ошибка при удалении профиля: {str(e)}", "error")
        return redirect(url_for("profile"))


@app.context_processor
def inject_globals():
    return dict(datetime=datetime)



if __name__ == "__main__":
    app.run(debug = True)   