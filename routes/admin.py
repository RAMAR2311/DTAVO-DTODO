from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Product, Sale, User, Category, ProductSeries, SaleDetail, DynamicKey, obtener_hora_bogota
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash
from decimal import Decimal
from decorators import admin_required
import string, random
from datetime import timedelta, datetime
import calendar

admin_bp = Blueprint('admin_bp', __name__)

@admin_bp.route('/generar-clave', methods=['POST'])
@login_required
@admin_required
def generar_clave():
    # Generar un código alfanumérico random de 6 caracteres
    codigo = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
    
    # Expiración: 10 minutos
    ahora = obtener_hora_bogota()
    expira = ahora + timedelta(minutes=10)
    
    nueva_clave = DynamicKey()
    nueva_clave.key_code = codigo
    nueva_clave.admin_id = current_user.id
    nueva_clave.created_at = ahora
    nueva_clave.expires_at = expira
    
    db.session.add(nueva_clave)
    db.session.commit()
    
    return jsonify({'success': True, 'codigo': codigo})

@admin_bp.route('/vendedores', methods=['GET', 'POST'])
@login_required
@admin_required
def vendedores():
    if request.method == 'POST':
        nombre = request.form.get('nombre')
        email = request.form.get('email')
        telefono = request.form.get('telefono')
        password = request.form.get('password')
        
        # Se previene registrar vendedores con un mismo email para preservar la unicidad de las credenciales de acceso
        if User.query.filter_by(email=email).first():
            flash('Acción Denegada: Ese correo ya le pertenece a otro vendedor.', 'danger')
        else:
            try:
                # Se aplica un hash a la contraseña para evitar guardar texto plano
                nuevo_vendedor = User()
                nuevo_vendedor.nombre = nombre.strip()
                nuevo_vendedor.email = email.strip()
                nuevo_vendedor.telefono = telefono.strip() if telefono else None
                nuevo_vendedor.password_hash = generate_password_hash(password)
                nuevo_vendedor.rol = 'vendedor'
                
                db.session.add(nuevo_vendedor)
                db.session.commit()
                flash(f"¡Vendedor '{nombre}' registrado y autorizado para Cajas!", "success")
            except Exception:
                db.session.rollback()
                flash('Ocurrió un error en la base de datos al intentar registrar al vendedor.', 'danger')
            
        return redirect(url_for('admin_bp.vendedores'))
        
    # Se pasa la lista para poblar la tabla HTML de gestión de personal
    lista_vendedores = User.query.filter_by(rol='vendedor').order_by(User.nombre).all()
    return render_template('admin/vendedores.html', vendedores=lista_vendedores)

@admin_bp.route('/vendedores/editar/<int:id>', methods=['POST'])
@login_required
@admin_required
def editar_vendedor(id):
    vendedor = User.query.get_or_404(id)
    nombre = request.form.get('nombre')
    email = request.form.get('email')
    telefono = request.form.get('telefono')
    password = request.form.get('password')
    
    # Validar email único si cambió
    if email != vendedor.email:
        if User.query.filter_by(email=email).first():
            flash('Error: El nuevo correo ya está en uso por otro usuario.', 'danger')
            return redirect(url_for('admin_bp.vendedores'))
 
    vendedor.nombre = nombre.strip()
    vendedor.email = email.strip()
    vendedor.telefono = telefono.strip() if telefono else None
    
    if password and password.strip():
        vendedor.password_hash = generate_password_hash(password)
        
    try:
        db.session.commit()
        flash(f'Vendedor "{nombre}" actualizado correctamente.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al actualizar el vendedor.', 'danger')
        
    return redirect(url_for('admin_bp.vendedores'))

@admin_bp.route('/vendedores/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_required
def eliminar_vendedor(id):
    vendedor = User.query.get_or_404(id)
    nombre = vendedor.nombre
    
    # No permitir que un admin borre a otro admin desde aquí o a sí mismo
    if vendedor.rol == 'admin':
        flash('No se pueden eliminar cuentas de administrador desde este panel.', 'danger')
        return redirect(url_for('admin_bp.vendedores'))

    try:
        db.session.delete(vendedor)
        db.session.commit()
        flash(f'Vendedor "{nombre}" eliminado con éxito.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error: No se pudo eliminar el vendedor (puede tener ventas u operaciones registradas).', 'danger')
        
    return redirect(url_for('admin_bp.vendedores'))

from flask import session

@admin_bp.route('/salir-nicho')
@login_required
def salir_nicho():
    session.pop('categoria_actual', None)
    session.pop('categoria_nombre', None)
    return redirect(url_for('index'))

@admin_bp.route('/dashboard')
@login_required
@admin_required
def dashboard():
    # 1. Obtener nicho de la sesión (contexto persistente)
    nicho_sesion = session.get('categoria_actual')
    nicho_nombre_sesion = session.get('categoria_nombre')
    
    # 2. Obtener nicho del filtro (contexto temporal)
    # Si viene por URL (?categoria_id=X), tiene prioridad para la vista actual
    nicho_filtro = request.args.get('categoria_id')
    
    # El nicho que usaremos para las consultas
    nicho_para_consulta = nicho_filtro if nicho_filtro else nicho_sesion
    
    # Convertir a int si existe y no es "todas"
    if nicho_para_consulta and nicho_para_consulta != 'todas':
        try:
            nicho_para_consulta = int(nicho_para_consulta)
        except ValueError:
            nicho_para_consulta = None
    else:
        nicho_para_consulta = None

    # Base de productos (Solo tienda)
    query_prod = Product.query.filter_by(tipo_inventario='tienda')
    query_sales_base = db.session.query(
        func.sum(SaleDetail.precio_venta_final * SaleDetail.cantidad_vendida)
    ).join(Sale)

    # APLICAR FILTRO DE NICHO
    if nicho_para_consulta:
        query_prod = query_prod.filter_by(categoria_id=nicho_para_consulta)
        query_sales_base = query_sales_base.filter(Sale.categoria_id == nicho_para_consulta)

    # ── FILTRO DE MES ────────────────────────────────────────────────
    hoy = obtener_hora_bogota()
    # Leer el mes del URL (?mes=YYYY-MM). Por defecto: mes actual.
    mes_param = request.args.get('mes', '').strip()
    if mes_param:
        try:
            anio_f, mes_f = int(mes_param[:4]), int(mes_param[5:7])
        except (ValueError, IndexError):
            anio_f, mes_f = hoy.year, hoy.month
    else:
        anio_f, mes_f = hoy.year, hoy.month

    # Rango exacto del mes seleccionado
    inicio_mes = datetime(anio_f, mes_f, 1, 0, 0, 0)
    ultimo_dia = calendar.monthrange(anio_f, mes_f)[1]
    fin_mes    = datetime(anio_f, mes_f, ultimo_dia, 23, 59, 59)

    # String para el input type="month" del formulario (YYYY-MM)
    mes_filtro_str = f"{anio_f:04d}-{mes_f:02d}"

    # Nombre legible del mes para mostrar en las tarjetas
    MESES_ES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    mes_nombre = f"{MESES_ES[mes_f - 1]} {anio_f}"

    # ── CÁLCULOS DEL MES SELECCIONADO ───────────────────────────────
    ventas_mes = query_sales_base.filter(
        Sale.fecha_venta >= inicio_mes,
        Sale.fecha_venta <= fin_mes
    ).scalar() or Decimal('0.0')

    # Número de ventas y ticket promedio del mes
    q_count = db.session.query(func.count(Sale.id)).filter(
        Sale.fecha_venta >= inicio_mes,
        Sale.fecha_venta <= fin_mes
    )
    if nicho_para_consulta:
        q_count = q_count.filter(Sale.categoria_id == nicho_para_consulta)
    num_ventas_mes = q_count.scalar() or 0
    ticket_promedio = (ventas_mes / num_ventas_mes) if num_ventas_mes > 0 else Decimal('0.0')

    # Mes anterior para comparativa
    if mes_f == 1:
        anio_ant, mes_ant = anio_f - 1, 12
    else:
        anio_ant, mes_ant = anio_f, mes_f - 1
    inicio_mes_ant = datetime(anio_ant, mes_ant, 1, 0, 0, 0)
    ultimo_dia_ant = calendar.monthrange(anio_ant, mes_ant)[1]
    fin_mes_ant    = datetime(anio_ant, mes_ant, ultimo_dia_ant, 23, 59, 59)
    ventas_mes_ant = query_sales_base.filter(
        Sale.fecha_venta >= inicio_mes_ant,
        Sale.fecha_venta <= fin_mes_ant
    ).scalar() or Decimal('0.0')

    # Variacion porcentual vs mes anterior
    if ventas_mes_ant > 0:
        variacion_pct = ((ventas_mes - ventas_mes_ant) / ventas_mes_ant) * 100
    else:
        variacion_pct = Decimal('0.0') if ventas_mes == 0 else Decimal('100.0')

    # Determinar si estamos en "modo celular" para mostrar la trazabilidad de IMEIs
    # Lógica: los IDs 1 y 6 son las categorías de celulares según el POS,
    # pero también detectamos por nombre para mayor robustez
    CATEGORIAS_CELULAR_IDS = {1, 6}
    es_modo_celular = False
    if nicho_para_consulta:
        if nicho_para_consulta in CATEGORIAS_CELULAR_IDS:
            es_modo_celular = True
        else:
            # Verificar por nombre de categoría (ej: "Celulares", "Celular", etc.)
            cat_activa = Category.query.get(nicho_para_consulta)
            if cat_activa and 'celular' in cat_activa.nombre.lower():
                es_modo_celular = True

    # Query de últimos IMEIs vendidos — solo se ejecuta en modo celular
    # Join correcto: ProductSeries -> SaleDetail (por sale_detail_id) -> Sale
    ultimos_imeis = []
    if es_modo_celular:
        ultimos_imeis = (
            db.session.query(ProductSeries, SaleDetail, Sale)
            .join(SaleDetail, ProductSeries.sale_detail_id == SaleDetail.id)
            .join(Sale, SaleDetail.sale_id == Sale.id)
            .filter(
                ProductSeries.estado == 'vendido',
                Sale.categoria_id == nicho_para_consulta
            )
            .order_by(Sale.fecha_venta.desc())
            .limit(5)
            .all()
        )
    
    # Datos para el selector de filtros
    categorias = Category.query.order_by(Category.nombre).all()
    
    # Cálculos de inventario (independientes del mes)
    productos_tienda = query_prod.all()
    total_productos = len(productos_tienda)
    productos_bajo_stock = sum(1 for p in productos_tienda if p.total_stock <= 3)

    return render_template('admin/dashboard.html',
                           # Inventario
                           total_productos=total_productos,
                           productos_bajo_stock=productos_bajo_stock,
                           # Ventas del mes seleccionado
                           ventas_mes=ventas_mes,
                           num_ventas_mes=num_ventas_mes,
                           ticket_promedio=ticket_promedio,
                           ventas_mes_ant=ventas_mes_ant,
                           variacion_pct=variacion_pct,
                           # Contexto de fecha
                           mes_filtro_str=mes_filtro_str,
                           mes_nombre=mes_nombre,
                           # Nicho
                           nicho_nombre=nicho_nombre_sesion,
                           nicho_activo=nicho_sesion,
                           filtro_actual=nicho_para_consulta,
                           categorias=categorias,
                           # IMEIs
                           ultimos_imeis=ultimos_imeis,
                           es_modo_celular=es_modo_celular)

# RUTAS DESACTIVADAS PARA EL ESQUELETO FUNCIONAL
@admin_bp.route('/vendedores')
@admin_bp.route('/perdidas')
@admin_bp.route('/maneos')
@admin_bp.route('/balance-financiero')
@login_required
@admin_required
def modulo_desactivado(*args, **kwargs):
    flash('Este módulo no está disponible en la versión simplificada del sistema.', 'info')
    return redirect(url_for('admin_bp.dashboard'))
