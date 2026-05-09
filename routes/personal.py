from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from models import db, User
from werkzeug.security import generate_password_hash
from decorators import admin_required

personal_bp = Blueprint('personal_bp', __name__)

@personal_bp.route('/', methods=['GET'])
@login_required
@admin_required
def index():
    usuarios = User.query.order_by(User.rol.asc(), User.nombre.asc()).all()
    return render_template('personal/index.html', usuarios=usuarios)

@personal_bp.route('/crear', methods=['POST'])
@login_required
@admin_required
def crear():
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    telefono = request.form.get('telefono')
    password = request.form.get('password')
    rol = request.form.get('rol', 'vendedor')

    if not nombre or not email or not password:
        flash('Por favor complete todos los campos obligatorios.', 'danger')
        return redirect(url_for('personal_bp.index'))

    if User.query.filter_by(email=email).first():
        flash('El correo electrónico ya está registrado.', 'danger')
        return redirect(url_for('personal_bp.index'))

    nuevo_usuario = User(
        nombre=nombre,
        email=email,
        telefono=telefono,
        password_hash=generate_password_hash(password),
        rol=rol
    )

    try:
        db.session.add(nuevo_usuario)
        db.session.commit()
        flash(f'Acceso otorgado a {nombre} exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al crear el usuario: {str(e)}', 'danger')

    return redirect(url_for('personal_bp.index'))

@personal_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar(id):
    if id == current_user.id:
        flash('No puedes eliminarte a ti mismo.', 'danger')
        return redirect(url_for('personal_bp.index'))

    usuario = User.query.get_or_404(id)
    nombre = usuario.nombre
    
    try:
        db.session.delete(usuario)
        db.session.commit()
        flash(f'Usuario {nombre} eliminado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'No se puede eliminar el usuario porque tiene registros asociados (ventas, etc).', 'danger')

    return redirect(url_for('personal_bp.index'))

@personal_bp.route('/editar/<int:id>', methods=['POST'])
@login_required
@admin_required
def editar(id):
    usuario = User.query.get_or_404(id)
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    telefono = request.form.get('telefono')
    rol = request.form.get('rol')
    password = request.form.get('password')

    if not nombre or not email:
        flash('Nombre y correo son obligatorios.', 'danger')
        return redirect(url_for('personal_bp.index'))

    # Verificar si el email ya existe en otro usuario
    check_email = User.query.filter(User.email == email, User.id != id).first()
    if check_email:
        flash('El correo electrónico ya está en uso por otro usuario.', 'danger')
        return redirect(url_for('personal_bp.index'))

    usuario.nombre = nombre
    usuario.email = email
    usuario.telefono = telefono
    usuario.rol = rol

    if password and password.strip():
        usuario.password_hash = generate_password_hash(password)

    try:
        db.session.commit()
        flash(f'Usuario {nombre} actualizado correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al actualizar: {str(e)}', 'danger')

    return redirect(url_for('personal_bp.index'))
