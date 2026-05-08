# Application entry point - Sanitized
import os
from flask import Flask, render_template, flash
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from models import db, User, obtener_hora_bogota
from dotenv import load_dotenv

load_dotenv()

def create_app():
    app = Flask(__name__)
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-bendito')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost/DTAVO')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    db.init_app(app)
    migrate = Migrate(app, db)
    csrf = CSRFProtect(app)
    
    login_manager = LoginManager()
    login_manager.login_view = 'auth_bp.login'
    login_manager.login_message = None  # Elimina el mensaje "Please log in to access this page"
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Registro de Blueprints
    from routes.personal import personal_bp
    from routes.sales import sales_bp
    from routes.inventory import inventory_bp
    from routes.auth import auth_bp
    from routes.arqueo import arqueo_bp
    from routes.gastos import gastos_bp
    # from routes.warranties import warranties_bp
    # from routes.importaciones import importaciones_bp
    from routes.clientes import clientes_bp
    from routes.providers import providers_bp
    
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(arqueo_bp, url_prefix='/arqueo')
    app.register_blueprint(gastos_bp, url_prefix='/gastos')
    # app.register_blueprint(warranties_bp, url_prefix='/garantias')
    # app.register_blueprint(importaciones_bp, url_prefix='/importaciones')
    app.register_blueprint(clientes_bp, url_prefix='/clientes')
    app.register_blueprint(providers_bp, url_prefix='/proveedores')
    app.register_blueprint(personal_bp, url_prefix='/personal')
    
    # Registro de Blueprint Admin
    from routes.admin import admin_bp
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # Registro de Blueprint Bodega (Removido para esqueleto simple)
    # from routes.bodega import bodega_bp
    # app.register_blueprint(bodega_bp, url_prefix='/bodega')

    @app.template_filter('cop')
    def cop_filter(value):
        if value is None:
            return "0"
        try:
            return "{:,.0f}".format(float(value))
        except (ValueError, TypeError):
            return value

    from flask_login import login_required

    from flask import session, redirect, url_for
    from models import Category

    @app.route('/')
    @login_required
    def index():
        # Si el usuario ya eligió un nicho, lo mandamos al dashboard
        if 'categoria_actual' in session:
            return redirect(url_for('admin_bp.dashboard'))
        
        # Si no, mostramos el Hub de categorías
        categorias = Category.query.all()
        return render_template('hub.html', categorias=categorias)

    @app.route('/seleccionar_nicho/<int:categoria_id>')
    @login_required
    def seleccionar_nicho(categoria_id):
        cat = Category.query.get_or_404(categoria_id)
        session['categoria_actual'] = cat.id
        session['categoria_nombre'] = cat.nombre
        return redirect(url_for('admin_bp.dashboard'))

    @app.route('/salir_nicho')
    @login_required
    def salir_nicho():
        session.pop('categoria_actual', None)
        session.pop('categoria_nombre', None)
        return redirect(url_for('index'))

    return app

app = create_app()

if __name__ == '__main__':
    app.run(debug=True)
