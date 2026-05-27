import os
from flask import Flask, render_template, session, redirect, url_for
from flask_migrate import Migrate
from flask_login import LoginManager, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from dotenv import load_dotenv

# Importar base de datos y modelos
from models import db, User, Category

load_dotenv()

# Inicialización global de extensiones
migrate = Migrate()
csrf = CSRFProtect()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)

    # 1. MEJORA: Configuración Proxy para HTTPS (Vital para Nginx + SSL)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # 2. Configuración de la Aplicación
    app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev-key-bendito')
    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('DATABASE_URL', 'postgresql://postgres:postgres@localhost/DTAVO')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    # 3. MEJORA: Seguridad SSL para Cookies y CSRF
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['WTF_CSRF_TRUSTED_ORIGINS'] = ['https://dtavo-zenic.cloud', 'https://www.dtavo-zenic.cloud']

    # 4. Inicialización de Extensiones
    db.init_app(app)
    migrate.init_app(app, db)
    csrf.init_app(app)
    
    login_manager.login_view = 'auth_bp.login'
    login_manager.login_message = None  
    login_manager.init_app(app)

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # 5. Registro de Blueprints (Ajustado a tu estructura de carpeta 'routes')
    from routes.personal import personal_bp
    from routes.sales import sales_bp
    from routes.inventory import inventory_bp
    from routes.auth import auth_bp
    from routes.arqueo import arqueo_bp
    from routes.gastos import gastos_bp
    from routes.clientes import clientes_bp
    from routes.providers import providers_bp
    from routes.admin import admin_bp
    
    app.register_blueprint(sales_bp, url_prefix='/sales')
    app.register_blueprint(inventory_bp, url_prefix='/inventory')
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(arqueo_bp, url_prefix='/arqueo')
    app.register_blueprint(gastos_bp, url_prefix='/gastos')
    app.register_blueprint(clientes_bp, url_prefix='/clientes')
    app.register_blueprint(providers_bp, url_prefix='/proveedores')
    app.register_blueprint(personal_bp, url_prefix='/personal')
    app.register_blueprint(admin_bp, url_prefix='/admin')

    # 6. Filtros Personalizados
    @app.template_filter('cop')
    def cop_filter(value):
        if value is None:
            return "0"
        try:
            return "{:,.0f}".format(float(value))
        except (ValueError, TypeError):
            return value

    # --- 7. RUTAS PRINCIPALES Y LÓGICA DE NICHOS ---

    @app.route('/')
    @login_required
    def index():
        # Si el usuario ya eligió un nicho, lo mandamos a su pantalla correspondiente
        if 'categoria_actual' in session:
            if current_user.rol == 'vendedor':
                return redirect(url_for('sales_bp.pos_visual'))
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
        if current_user.rol == 'vendedor':
            return redirect(url_for('sales_bp.pos_visual'))
        return redirect(url_for('admin_bp.dashboard'))

    @app.route('/salir_nicho')
    @login_required
    def salir_nicho():
        session.pop('categoria_actual', None)
        session.pop('categoria_nombre', None)
        return redirect(url_for('index'))

    return app

# Instancia global para Gunicorn
app = create_app()

if __name__ == '__main__':
    # En producción debug debe ser False, pero lo dejo como tu original
    app.run(debug=True)