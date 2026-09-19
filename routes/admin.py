from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from models import (
    db, Product, Sale, User, Category, ProductSeries, SaleDetail, 
    DynamicKey, SalePayment, Expense, Provider, ProviderInvoice, ProviderPayment,
    obtener_hora_bogota
)
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

    # ── FILTRO DE PERÍODO (Semana, Quincena, Mes, Histórico) ────────
    hoy = obtener_hora_bogota()
    MESES_ES = ['Enero','Febrero','Marzo','Abril','Mayo','Junio',
                'Julio','Agosto','Septiembre','Octubre','Noviembre','Diciembre']
    
    periodo_param = request.args.get('periodo', '').strip() or request.args.get('mes', '').strip() or 'mes'

    if periodo_param == 'semana':
        # Esta semana (Lunes 00:00:00 a Domingo 23:59:59)
        dias_desde_lunes = hoy.weekday()
        inicio_periodo = (hoy - timedelta(days=dias_desde_lunes)).replace(hour=0, minute=0, second=0, microsecond=0)
        fin_periodo = (inicio_periodo + timedelta(days=6)).replace(hour=23, minute=59, second=59, microsecond=999999)
        periodo_nombre = f"Esta Semana ({inicio_periodo.strftime('%d %b')} - {fin_periodo.strftime('%d %b')})"
        periodo_tag = "Semana Actual"
        comparativa_label = "Semana anterior"

        # Comparativa vs semana anterior
        inicio_ant = inicio_periodo - timedelta(days=7)
        fin_ant = inicio_periodo - timedelta(seconds=1)

    elif periodo_param == 'quincena':
        # Esta Quincena (1-15 o 16 al fin de mes)
        if hoy.day <= 15:
            inicio_periodo = datetime(hoy.year, hoy.month, 1, 0, 0, 0)
            fin_periodo = datetime(hoy.year, hoy.month, 15, 23, 59, 59)
            periodo_nombre = f"1ra Quincena {MESES_ES[hoy.month - 1]} (1-15)"
            periodo_tag = "1ra Quincena"
            comparativa_label = "Quincena anterior"

            # Comparativa vs 2da quincena mes anterior
            m_ant = 12 if hoy.month == 1 else hoy.month - 1
            y_ant = hoy.year - 1 if hoy.month == 1 else hoy.year
            u_ant = calendar.monthrange(y_ant, m_ant)[1]
            inicio_ant = datetime(y_ant, m_ant, 16, 0, 0, 0)
            fin_ant = datetime(y_ant, m_ant, u_ant, 23, 59, 59)
        else:
            u_mes = calendar.monthrange(hoy.year, hoy.month)[1]
            inicio_periodo = datetime(hoy.year, hoy.month, 16, 0, 0, 0)
            fin_periodo = datetime(hoy.year, hoy.month, u_mes, 23, 59, 59)
            periodo_nombre = f"2da Quincena {MESES_ES[hoy.month - 1]} (16-{u_mes})"
            periodo_tag = "2da Quincena"
            comparativa_label = "1ra Quincena del mes"

            # Comparativa vs 1ra quincena mismo mes
            inicio_ant = datetime(hoy.year, hoy.month, 1, 0, 0, 0)
            fin_ant = datetime(hoy.year, hoy.month, 15, 23, 59, 59)

    elif periodo_param in ['mes', 'este_mes'] or periodo_param == f"{hoy.year:04d}-{hoy.month:02d}":
        # Mes actual completo
        inicio_periodo = datetime(hoy.year, hoy.month, 1, 0, 0, 0)
        ultimo_dia = calendar.monthrange(hoy.year, hoy.month)[1]
        fin_periodo = datetime(hoy.year, hoy.month, ultimo_dia, 23, 59, 59)
        periodo_nombre = f"Este Mes ({MESES_ES[hoy.month - 1]} {hoy.year})"
        periodo_tag = f"{MESES_ES[hoy.month - 1]} {hoy.year}"
        comparativa_label = "Mes anterior"
        periodo_param = 'mes'

        # Comparativa vs mes anterior
        m_ant = 12 if hoy.month == 1 else hoy.month - 1
        y_ant = hoy.year - 1 if hoy.month == 1 else hoy.year
        u_ant = calendar.monthrange(y_ant, m_ant)[1]
        inicio_ant = datetime(y_ant, m_ant, 1, 0, 0, 0)
        fin_ant = datetime(y_ant, m_ant, u_ant, 23, 59, 59)

    else:
        # Mes histórico específico (YYYY-MM)
        try:
            anio_f, mes_f = int(periodo_param[:4]), int(periodo_param[5:7])
        except (ValueError, IndexError):
            anio_f, mes_f = hoy.year, hoy.month
        
        inicio_periodo = datetime(anio_f, mes_f, 1, 0, 0, 0)
        ultimo_dia = calendar.monthrange(anio_f, mes_f)[1]
        fin_periodo = datetime(anio_f, mes_f, ultimo_dia, 23, 59, 59)
        periodo_nombre = f"{MESES_ES[mes_f - 1]} {anio_f}"
        periodo_tag = f"{MESES_ES[mes_f - 1]} {anio_f}"
        comparativa_label = "Mes anterior"

        # Comparativa vs mes anterior al seleccionado
        m_ant = 12 if mes_f == 1 else mes_f - 1
        y_ant = anio_f - 1 if mes_f == 1 else anio_f
        u_ant = calendar.monthrange(y_ant, m_ant)[1]
        inicio_ant = datetime(y_ant, m_ant, 1, 0, 0, 0)
        fin_ant = datetime(y_ant, m_ant, u_ant, 23, 59, 59)

    # ── CÁLCULOS DEL PERÍODO SELECCIONADO ───────────────────────────
    ventas_mes = query_sales_base.filter(
        Sale.fecha_venta >= inicio_periodo,
        Sale.fecha_venta <= fin_periodo
    ).scalar() or Decimal('0.0')

    # Número de ventas y ticket promedio
    q_count = db.session.query(func.count(Sale.id)).filter(
        Sale.fecha_venta >= inicio_periodo,
        Sale.fecha_venta <= fin_periodo
    )
    if nicho_para_consulta:
        q_count = q_count.filter(Sale.categoria_id == nicho_para_consulta)
    num_ventas_mes = q_count.scalar() or 0
    ticket_promedio = (ventas_mes / num_ventas_mes) if num_ventas_mes > 0 else Decimal('0.0')

    # ── DESGLOSE DE INGRESOS (Efectivo vs. Transferencias/Bancos) ────
    q_pagos = db.session.query(
        SalePayment.metodo_pago,
        func.sum(SalePayment.monto)
    ).join(Sale).filter(
        Sale.fecha_venta >= inicio_periodo,
        Sale.fecha_venta <= fin_periodo
    )
    if nicho_para_consulta:
        q_pagos = q_pagos.filter(Sale.categoria_id == nicho_para_consulta)
    
    pagos_res = dict(q_pagos.group_by(SalePayment.metodo_pago).all())
    ingresos_efectivo = pagos_res.get('efectivo', Decimal('0.0'))
    ingresos_transferencia = sum(v for k, v in pagos_res.items() if k != 'efectivo')

    if not pagos_res and ventas_mes > 0:
        ingresos_efectivo = ventas_mes
        ingresos_transferencia = Decimal('0.0')

    # ── MERCANCÍA VENDIDA (Unidades y Referencias únicas) ───────────
    q_items = db.session.query(
        func.sum(SaleDetail.cantidad_vendida),
        func.count(func.distinct(SaleDetail.product_id))
    ).join(Sale).filter(
        Sale.fecha_venta >= inicio_periodo,
        Sale.fecha_venta <= fin_periodo
    )
    if nicho_para_consulta:
        q_items = q_items.filter(Sale.categoria_id == nicho_para_consulta)
    
    uds_res, refs_res = q_items.first() or (0, 0)
    unidades_vendidas = uds_res or 0
    referencias_vendidas = refs_res or 0

    # ── COSTO DE MERCANCÍA VENDIDA (COGS) ────────────────────────────
    q_cogs = db.session.query(
        func.sum(SaleDetail.cantidad_vendida * func.coalesce(Product.precio_costo, 0))
    ).join(Sale, SaleDetail.sale_id == Sale.id)\
     .join(Product, SaleDetail.product_id == Product.id)\
     .filter(
        Sale.fecha_venta >= inicio_periodo,
        Sale.fecha_venta <= fin_periodo
    )
    if nicho_para_consulta:
        q_cogs = q_cogs.filter(Sale.categoria_id == nicho_para_consulta)
    costo_mercancia = q_cogs.scalar() or Decimal('0.0')

    # ── GASTOS DEL PERÍODO (Egresos Operativos) ──────────────────────
    q_gastos = db.session.query(
        Expense.tipo,
        func.sum(Expense.monto)
    ).filter(
        Expense.fecha >= inicio_periodo,
        Expense.fecha <= fin_periodo
    )
    gastos_dict = dict(q_gastos.group_by(Expense.tipo).all())
    gastos_diarios = gastos_dict.get('Gasto Diario', Decimal('0.0'))
    gastos_indirectos = sum(v for k, v in gastos_dict.items() if k != 'Gasto Diario')
    total_gastos = sum(gastos_dict.values()) if gastos_dict else Decimal('0.0')

    # ── UTILIDAD ESTIMADA & MÁRGENES FINANCIEROS ─────────────────────
    margen_bruto = Decimal(ventas_mes) - Decimal(costo_mercancia)
    utilidad_estimada = margen_bruto - Decimal(total_gastos)
    margen_pct = ((utilidad_estimada / ventas_mes) * 100) if ventas_mes > 0 else Decimal('0.0')
    margen_bruto_pct = ((margen_bruto / ventas_mes) * 100) if ventas_mes > 0 else Decimal('0.0')

    # ── COMPARATIVA PERÍODO ANTERIOR ────────────────────────────────
    ventas_mes_ant = query_sales_base.filter(
        Sale.fecha_venta >= inicio_ant,
        Sale.fecha_venta <= fin_ant
    ).scalar() or Decimal('0.0')

    # Variación porcentual
    if ventas_mes_ant > 0:
        variacion_pct = ((ventas_mes - ventas_mes_ant) / ventas_mes_ant) * 100
    else:
        variacion_pct = Decimal('0.0') if ventas_mes == 0 else Decimal('100.0')

    # Determinar si estamos en "modo celular"
    CATEGORIAS_CELULAR_IDS = {1, 6}
    es_modo_celular = False
    if nicho_para_consulta:
        if nicho_para_consulta in CATEGORIAS_CELULAR_IDS:
            es_modo_celular = True
        else:
            cat_activa = Category.query.get(nicho_para_consulta)
            if cat_activa and 'celular' in cat_activa.nombre.lower():
                es_modo_celular = True

    # Query de últimos IMEIs vendidos
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
    
    # Cálculos de inventario
    productos_tienda = query_prod.all()
    total_productos = len(productos_tienda)
    productos_bajo_stock = sum(1 for p in productos_tienda if p.es_stock_bajo)
    productos_criticos = sum(1 for p in productos_tienda if p.total_stock <= 10)

    # ── ABONOS Y CUENTAS A PROVEEDORES ───────────────────────────────
    abonos_prov_mes = db.session.query(
        func.sum(ProviderPayment.monto)
    ).filter(
        ProviderPayment.fecha >= inicio_periodo,
        ProviderPayment.fecha <= fin_periodo
    ).scalar() or Decimal('0.0')
    total_proveedores = Provider.query.count()
    facturas_pendientes_prov = ProviderInvoice.query.count()

    # ── APROBACIONES DE PRECIO / CLAVES DINÁMICAS ────────────────────
    claves_mes = DynamicKey.query.filter(
        DynamicKey.created_at >= inicio_periodo,
        DynamicKey.created_at <= fin_periodo
    ).count()
    claves_activas = DynamicKey.query.filter(
        DynamicKey.is_used == False,
        DynamicKey.expires_at > hoy
    ).count()

    # ── ÚLTIMAS VENTAS RECIENTES (Auditoría en tiempo real) ───────────
    q_ultimas_ventas = Sale.query.order_by(Sale.fecha_venta.desc())
    if nicho_para_consulta:
        q_ultimas_ventas = q_ultimas_ventas.filter_by(categoria_id=nicho_para_consulta)
    ultimas_ventas = q_ultimas_ventas.limit(6).all()

    # Lista de meses anteriores para el histórico en el desplegable (desde el mes pasado hacia atrás)
    meses_anteriores = []
    c_anio, c_mes = hoy.year, hoy.month
    # Retroceder 1 mes para empezar desde el mes anterior
    if c_mes == 1:
        c_mes = 12
        c_anio -= 1
    else:
        c_mes -= 1

    for _ in range(24):
        m_str = f"{c_anio:04d}-{c_mes:02d}"
        m_nom = f"{MESES_ES[c_mes - 1]} {c_anio}"
        meses_anteriores.append({'val': m_str, 'nombre': m_nom})
        if c_mes == 1:
            c_mes = 12
            c_anio -= 1
        else:
            c_mes -= 1

    mes_actual_nombre = f"{MESES_ES[hoy.month - 1]} {hoy.year}"
    mes_actual_str = f"{hoy.year:04d}-{hoy.month:02d}"

    return render_template('admin/dashboard.html',
                           # Inventario
                           total_productos=total_productos,
                           productos_bajo_stock=productos_bajo_stock,
                           productos_criticos=productos_criticos,
                           # Ventas del período seleccionado
                           ventas_mes=ventas_mes,
                           num_ventas_mes=num_ventas_mes,
                           ticket_promedio=ticket_promedio,
                           ventas_mes_ant=ventas_mes_ant,
                           variacion_pct=variacion_pct,
                           comparativa_label=comparativa_label,
                           # Desglose de Ingresos
                           ingresos_efectivo=ingresos_efectivo,
                           ingresos_transferencia=ingresos_transferencia,
                           # Mercancía
                           unidades_vendidas=unidades_vendidas,
                           referencias_vendidas=referencias_vendidas,
                           costo_mercancia=costo_mercancia,
                           # Gastos y Utilidad
                           total_gastos=total_gastos,
                           gastos_diarios=gastos_diarios,
                           gastos_indirectos=gastos_indirectos,
                           utilidad_estimada=utilidad_estimada,
                           margen_bruto=margen_bruto,
                           margen_pct=margen_pct,
                           margen_bruto_pct=margen_bruto_pct,
                           # Proveedores y Claves
                           abonos_prov_mes=abonos_prov_mes,
                           total_proveedores=total_proveedores,
                           facturas_pendientes_prov=facturas_pendientes_prov,
                           claves_mes=claves_mes,
                           claves_activas=claves_activas,
                           # Ventas recientes
                           ultimas_ventas=ultimas_ventas,
                           # Contexto de período
                           periodo_filtro=periodo_param,
                           periodo_nombre=periodo_nombre,
                           periodo_tag=periodo_tag,
                           mes_actual_nombre=mes_actual_nombre,
                           mes_actual_str=mes_actual_str,
                           meses_anteriores=meses_anteriores,
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
