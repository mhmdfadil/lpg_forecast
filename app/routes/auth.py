"""
Route untuk autentikasi admin: login, logout, ubah password/profil.
"""
from flask import Blueprint, render_template, request, redirect, url_for, session, flash
from app.models.admin import (
    get_admin_by_username,
    get_admin_by_id,
    verify_password,
    touch_last_login,
    update_password,
    update_profile,
)
from app.utils.decorators import login_required

auth_bp = Blueprint("auth", __name__, url_prefix="")


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if "admin_id" in session:
        return redirect(url_for("dashboard.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        password = request.form.get("password") or ""

        if not username or not password:
            flash("Username dan password wajib diisi.", "danger")
            return render_template("auth/login.html")

        try:
            admin = get_admin_by_username(username)
        except Exception as e:
            flash(f"Gagal terhubung ke database: {e}", "danger")
            return render_template("auth/login.html")

        if not admin or not admin.get("is_active", True):
            flash("Username atau password salah.", "danger")
            return render_template("auth/login.html")

        if not verify_password(password, admin["password_hash"]):
            flash("Username atau password salah.", "danger")
            return render_template("auth/login.html")

        session.permanent = True
        session["admin_id"] = admin["id"]
        session["admin_name"] = admin.get("full_name") or admin["username"]
        session["admin_username"] = admin["username"]

        try:
            touch_last_login(admin["id"])
        except Exception:
            pass

        flash(f"Selamat datang kembali, {session['admin_name']}!", "success")
        next_url = request.args.get("next") or url_for("dashboard.index")
        return redirect(next_url)

    return render_template("auth/login.html")


@auth_bp.route("/logout")
def logout():
    session.clear()
    flash("Anda telah berhasil logout.", "info")
    return redirect(url_for("auth.login"))


@auth_bp.route("/profil", methods=["GET", "POST"])
@login_required
def profile():
    admin = get_admin_by_id(session["admin_id"])

    if request.method == "POST":
        action = request.form.get("action")

        if action == "update_profile":
            full_name = request.form.get("full_name", "").strip()
            email = request.form.get("email", "").strip()
            update_profile(session["admin_id"], full_name=full_name, email=email)
            session["admin_name"] = full_name or session["admin_username"]
            flash("Profil berhasil diperbarui.", "success")
            return redirect(url_for("auth.profile"))

        elif action == "change_password":
            current_password = request.form.get("current_password", "")
            new_password = request.form.get("new_password", "")
            confirm_password = request.form.get("confirm_password", "")

            if not verify_password(current_password, admin["password_hash"]):
                flash("Password saat ini salah.", "danger")
            elif len(new_password) < 6:
                flash("Password baru minimal 6 karakter.", "danger")
            elif new_password != confirm_password:
                flash("Konfirmasi password baru tidak cocok.", "danger")
            else:
                update_password(session["admin_id"], new_password)
                flash("Password berhasil diubah.", "success")
            return redirect(url_for("auth.profile"))

    return render_template("auth/profile.html", admin=admin)
