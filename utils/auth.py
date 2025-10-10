from functools import wraps
from flask import session, redirect, url_for, flash
from models import User, db


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Сначала зарегистрируйтесь или выполните вход.", "warning")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            flash("Сначала зарегистрируйтесь или выполните вход.", "error")
            return redirect(url_for("login"))
        
        current_user = User.query.get(session["user_id"])
        if not current_user or current_user.role != "admin":
            flash("У вас нет доступа к этой странице.", "danger")
            return redirect(url_for("login"))
        
        return f(*args, **kwargs)
    return decorated_function
