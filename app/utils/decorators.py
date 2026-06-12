"""
Decorator & helper untuk proteksi route admin.
"""
from functools import wraps
from flask import session, redirect, url_for, flash, request


def login_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if "admin_id" not in session:
            flash("Silakan login terlebih dahulu untuk mengakses halaman ini.", "warning")
            return redirect(url_for("auth.login", next=request.path))
        return view_func(*args, **kwargs)
    return wrapped
