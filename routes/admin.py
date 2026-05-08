from flask import Blueprint, render_template, abort, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import db, Product, ProductVariant, Sale, User, Category, ProductSeries, Maneo, SaleDetail, SalePayment, StockAdjustment, Expense, Loss, Provider, ProviderInvoice, ProviderPayment, Warranty, DynamicKey, Importacion, ClienteCartera, FacturaCredito, AbonoCredito, obtener_hora_bogota
from sqlalchemy.sql import func
from werkzeug.security import generate_password_hash
from decimal import Decimal
from decorators import admin_required
import string, random
from datetime import timedelta

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
            except Exception as e:
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
    except Exception as e:
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
    except Exception as e:
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
    query_sales_base = db.session.query(func.sum(SaleDetail.precio_venta_final * SaleDetail.cantidad_vendida)).join(Sale)
    query_imeis = ProductSeries.query.filter_by(estado='vendido').join(SaleDetail).join(Sale)

    # APLICAR FILTRO
    if nicho_para_consulta:
        query_prod = query_prod.filter_by(categoria_id=nicho_para_consulta)
        query_sales_base = query_sales_base.filter(Sale.categoria_id == nicho_para_consulta)
        query_imeis = query_imeis.filter(Sale.categoria_id == nicho_para_consulta)

    # Cálculos
    productos_tienda = query_prod.all()
    total_productos = len(productos_tienda)
    productos_bajo_stock = sum(1 for p in productos_tienda if p.total_stock <= 3)
    total_ventas = query_sales_base.scalar() or Decimal('0.0')
    
    hoy = obtener_hora_bogota()
    mes_actual = hoy.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    ventas_mes_actual = query_sales_base.filter(Sale.fecha_venta >= mes_actual).scalar() or Decimal('0.0')
    ultimos_imeis = query_imeis.order_by(Sale.fecha_venta.desc()).limit(5).all()
    
    # Datos para el selector de filtros
    categorias = Category.query.order_by(Category.nombre).all()
    
    # DEBUG Dashboard - Validar tipos de datos para el selector
    print(f"DEBUG Dashboard - Valor sesión: {session.get('categoria_actual')} | Tipo: {type(session.get('categoria_actual'))}")
    print(f"DEBUG Dashboard - Valor filtro: {nicho_para_consulta} | Tipo: {type(nicho_para_consulta)}")

    return render_template('admin/dashboard.html', 
                           total_productos=total_productos,
                           productos_bajo_stock=productos_bajo_stock,
                           total_ventas=total_ventas,
                           ventas_mes_actual=ventas_mes_actual,
                           nicho_nombre=nicho_nombre_sesion,
                           nicho_activo=nicho_sesion,
                           filtro_actual=nicho_para_consulta,
                           categorias=categorias,
                           ultimos_imeis=ultimos_imeis)

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
