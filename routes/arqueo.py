# -*- coding: utf-8 -*-
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Sale, SalePayment, SaleDetail, Product, Category, ArqueoCaja, Expense
from datetime import datetime, time, timedelta, date
import pytz
from sqlalchemy import func
from decorators import admin_required

arqueo_bp = Blueprint('arqueo_bp', __name__)

def obtener_hora_bogota():
    return datetime.now(pytz.timezone('America/Bogota')).replace(tzinfo=None)

@arqueo_bp.route('/')
@login_required
@admin_required
def index():
    # Por defecto sugerimos el día de hoy en Bogotá
    hoy = obtener_hora_bogota().strftime('%Y-%m-%d')
    return render_template('admin/arqueo.html', hoy=hoy)

@arqueo_bp.route('/datos-dia', methods=['GET'])
@login_required
@admin_required
def datos_dia():
    fecha_str = request.args.get('fecha')
    if not fecha_str:
        fecha_str = obtener_hora_bogota().strftime('%Y-%m-%d')
    
    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"error": "Formato de fecha inválido. Use YYYY-MM-DD"}), 400

    # Verificar si ya existe un arqueo guardado para esa fecha
    arqueo_existente = ArqueoCaja.query.filter_by(fecha_arqueo=fecha_obj).first()
    
    if arqueo_existente:
        return jsonify({
            "ya_cerrado": True,
            "arqueo_guardado": {
                "id": arqueo_existente.id,
                "vendedor": arqueo_existente.cajero.nombre if arqueo_existente.cajero else "Desconocido",
                "fecha_arqueo": arqueo_existente.fecha_arqueo.strftime('%Y-%m-%d'),
                "base_inicial": float(arqueo_existente.base_inicial),
                "total_ventas": float(arqueo_existente.total_ventas),
                "gastos_del_dia": float(arqueo_existente.gastos_del_dia),
                "observaciones_gastos": arqueo_existente.observaciones_gastos or "",
                "total_efectivo_sistema": float(arqueo_existente.total_efectivo_sistema),
                "total_transferencia_sistema": float(arqueo_existente.total_transferencia_sistema),
                "efectivo_fisico": float(arqueo_existente.efectivo_fisico),
                "diferencia": float(arqueo_existente.diferencia),
                "observacion_diferencia": arqueo_existente.observacion_diferencia or "",
                "desglose_categorias": arqueo_existente.desglose_categorias or {},
                "desglose_pagos": arqueo_existente.desglose_pagos or {}
            }
        })

    # Rango de la fecha
    inicio_dia = datetime.combine(fecha_obj, time.min)
    fin_dia = datetime.combine(fecha_obj, time.max)

    # 1. Ventas por método de pago de este día
    totales_pago = db.session.query(
        SalePayment.metodo_pago,
        func.sum(SalePayment.monto).label('total')
    ).join(Sale, Sale.id == SalePayment.sale_id)\
     .filter(Sale.fecha_venta >= inicio_dia, Sale.fecha_venta <= fin_dia)\
     .group_by(SalePayment.metodo_pago).all()

    total_efectivo_sistema = 0.0
    total_transferencia_sistema = 0.0
    desglose_pagos = {}

    for metodo, total in totales_pago:
        monto = float(total)
        desglose_pagos[metodo] = monto
        if metodo == 'efectivo':
            total_efectivo_sistema += monto
        else:
            total_transferencia_sistema += monto

    # 2. Ventas por Nicho de este día
    ventas_por_nicho_raw = db.session.query(
        Category.nombre,
        func.sum(SaleDetail.cantidad_vendida * SaleDetail.precio_venta_final).label('total')
    ).select_from(SaleDetail)\
     .join(Sale, Sale.id == SaleDetail.sale_id)\
     .outerjoin(Product, Product.id == SaleDetail.product_id)\
     .outerjoin(Category, Category.id == Product.categoria_id)\
     .filter(Sale.fecha_venta >= inicio_dia, Sale.fecha_venta <= fin_dia)\
     .group_by(Category.nombre).all()

    desglose_categorias = {}
    for nombre, total in ventas_por_nicho_raw:
        cat_name = nombre if nombre else "Otros / Sin Categoría"
        desglose_categorias[cat_name] = float(total)

    # 3. Gastos de este día
    gastos_list = Expense.query.filter(Expense.fecha >= inicio_dia, Expense.fecha <= fin_dia).all()
    gastos_del_dia = sum(float(g.monto) for g in gastos_list)
    gastos_detalles = [{"categoria": g.categoria, "descripcion": g.descripcion, "monto": float(g.monto)} for g in gastos_list]

    # total_bruto = suma de nichos
    total_bruto = sum(item for item in desglose_categorias.values())

    return jsonify({
        "ya_cerrado": False,
        "fecha_arqueo": fecha_str,
        "total_efectivo_sistema": total_efectivo_sistema,
        "total_transferencia_sistema": total_transferencia_sistema,
        "gastos_del_dia": gastos_del_dia,
        "gastos_detalles": gastos_detalles,
        "desglose_categorias": desglose_categorias,
        "desglose_pagos": desglose_pagos,
        "total_bruto": total_bruto
    })

@arqueo_bp.route('/guardar', methods=['POST'])
@login_required
@admin_required
def guardar():
    data = request.form
    fecha_str = data.get('fecha_arqueo')
    if not fecha_str:
        flash("La fecha es obligatoria para registrar el arqueo.", "danger")
        return redirect(url_for('arqueo_bp.index'))
    
    try:
        fecha_obj = datetime.strptime(fecha_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Formato de fecha inválido.", "danger")
        return redirect(url_for('arqueo_bp.index'))

    # Verificar duplicado
    arqueo_existente = ArqueoCaja.query.filter_by(fecha_arqueo=fecha_obj).first()
    if arqueo_existente:
        flash(f"Ya existe un arqueo registrado para la fecha {fecha_str}.", "warning")
        return redirect(url_for('arqueo_bp.index'))

    base_inicial = float(data.get('base_inicial', 0))
    efectivo_fisico = float(data.get('efectivo_fisico', 0))
    observaciones_gastos = data.get('observaciones_gastos', '')
    observacion_diferencia = data.get('observacion_diferencia', '')

    # Recalcular por seguridad
    inicio_dia = datetime.combine(fecha_obj, time.min)
    fin_dia = datetime.combine(fecha_obj, time.max)

    # Ventas por pago
    totales_pago = db.session.query(
        SalePayment.metodo_pago,
        func.sum(SalePayment.monto).label('total')
    ).join(Sale, Sale.id == SalePayment.sale_id)\
     .filter(Sale.fecha_venta >= inicio_dia, Sale.fecha_venta <= fin_dia)\
     .group_by(SalePayment.metodo_pago).all()

    total_efectivo_sistema = 0.0
    total_transferencia_sistema = 0.0
    desglose_pagos = {}

    for metodo, total in totales_pago:
        monto = float(total)
        desglose_pagos[metodo] = monto
        if metodo == 'efectivo':
            total_efectivo_sistema += monto
        else:
            total_transferencia_sistema += monto

    # Ventas por nicho
    ventas_por_nicho_raw = db.session.query(
        Category.nombre,
        func.sum(SaleDetail.cantidad_vendida * SaleDetail.precio_venta_final).label('total')
    ).select_from(SaleDetail)\
     .join(Sale, Sale.id == SaleDetail.sale_id)\
     .outerjoin(Product, Product.id == SaleDetail.product_id)\
     .outerjoin(Category, Category.id == Product.categoria_id)\
     .filter(Sale.fecha_venta >= inicio_dia, Sale.fecha_venta <= fin_dia)\
     .group_by(Category.nombre).all()

    desglose_categorias = {}
    for nombre, total in ventas_por_nicho_raw:
        cat_name = nombre if nombre else "Otros / Sin Categoría"
        desglose_categorias[cat_name] = float(total)

    # Gastos de este día
    gastos_list = Expense.query.filter(Expense.fecha >= inicio_dia, Expense.fecha <= fin_dia).all()
    gastos_del_dia = sum(float(g.monto) for g in gastos_list)

    # Fórmulas
    efectivo_esperado = base_inicial + total_efectivo_sistema - gastos_del_dia
    diferencia = efectivo_fisico - efectivo_esperado

    if diferencia != 0.0 and not observacion_diferencia.strip():
        flash("La justificación de la diferencia (faltante o sobrante) es obligatoria.", "danger")
        return redirect(url_for('arqueo_bp.index'))

    # Crear registro
    nuevo_arqueo = ArqueoCaja(
        vendedor_id=current_user.id,
        fecha_arqueo=fecha_obj,
        base_inicial=base_inicial,
        gastos_del_dia=gastos_del_dia,
        observaciones_gastos=observaciones_gastos,
        total_efectivo_sistema=total_efectivo_sistema,
        total_transferencia_sistema=total_transferencia_sistema,
        efectivo_fisico=efectivo_fisico,
        diferencia=diferencia,
        observacion_diferencia=observacion_diferencia if diferencia != 0.0 else "Caja cuadrada sin novedades.",
        total_ventas=total_efectivo_sistema + total_transferencia_sistema,
        desglose_categorias=desglose_categorias,
        desglose_pagos=desglose_pagos
    )

    db.session.add(nuevo_arqueo)
    db.session.commit()

    flash(f"¡Cierre de caja registrado exitosamente para la fecha {fecha_str}!", "success")
    return redirect(url_for('admin_bp.dashboard'))

@arqueo_bp.route('/reporte', methods=['GET'])
@login_required
@admin_required
def reporte():
    fecha_inicio_str = request.args.get('fecha_inicio')
    fecha_fin_str = request.args.get('fecha_fin')
    
    timezone = pytz.timezone('America/Bogota')
    hoy = datetime.now(timezone).replace(tzinfo=None).date()
    
    if not fecha_inicio_str:
        fecha_inicio_str = (hoy - timedelta(days=30)).strftime('%Y-%m-%d')
    if not fecha_fin_str:
        fecha_fin_str = hoy.strftime('%Y-%m-%d')
        
    try:
        fecha_inicio = datetime.strptime(fecha_inicio_str, '%Y-%m-%d').date()
        fecha_fin = datetime.strptime(fecha_fin_str, '%Y-%m-%d').date()
    except ValueError:
        flash("Formato de rango de fechas inválido. Use YYYY-MM-DD", "danger")
        return redirect(url_for('arqueo_bp.index'))
        
    # Consultar arqueos
    arqueos = ArqueoCaja.query.filter(
        ArqueoCaja.fecha_arqueo >= fecha_inicio,
        ArqueoCaja.fecha_arqueo <= fecha_fin
    ).order_by(ArqueoCaja.fecha_arqueo.desc()).all()
    
    # Sumatorias globales
    total_base_inicial = sum(a.base_inicial for a in arqueos)
    total_ventas_brutas = sum(a.total_ventas for a in arqueos)
    total_efectivo_sistema = sum(a.total_efectivo_sistema for a in arqueos)
    total_transferencia_sistema = sum(a.total_transferencia_sistema for a in arqueos)
    total_gastos = sum(a.gastos_del_dia for a in arqueos)
    total_efectivo_fisico = sum(a.efectivo_fisico for a in arqueos)
    total_diferencia = sum(a.diferencia for a in arqueos)
    
    return render_template(
        'admin/arqueo_reporte.html',
        arqueos=arqueos,
        fecha_inicio=fecha_inicio_str,
        fecha_fin=fecha_fin_str,
        total_base_inicial=total_base_inicial,
        total_ventas_brutas=total_ventas_brutas,
        total_efectivo_sistema=total_efectivo_sistema,
        total_transferencia_sistema=total_transferencia_sistema,
        total_gastos=total_gastos,
        total_efectivo_fisico=total_efectivo_fisico,
        total_diferencia=total_diferencia
    )

@arqueo_bp.route('/historial')
@login_required
@admin_required
def historial():
    cierres = ArqueoCaja.query.order_by(ArqueoCaja.fecha_arqueo.desc()).all()
    return render_template('admin/arqueo_historial.html', cierres=cierres)

@arqueo_bp.route('/recibo/<int:arqueo_id>')
@login_required
@admin_required
def imprimir_recibo(arqueo_id):
    arqueo = ArqueoCaja.query.get_or_404(arqueo_id)
    return render_template('admin/arqueo_recibo.html', arqueo=arqueo)
