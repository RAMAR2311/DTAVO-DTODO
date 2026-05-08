
from flask import Blueprint, render_template, jsonify, request, flash, redirect, url_for
from flask_login import login_required, current_user
from models import db, Sale, SalePayment, SaleDetail, Product, Category, ArqueoCaja, Expense, User
from datetime import datetime, time
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
    # Encontramos el último arqueo para saber desde cuándo contar
    ultimo_arqueo = ArqueoCaja.query.order_by(ArqueoCaja.fecha_creacion.desc()).first()
    fecha_inicio = ultimo_arqueo.fecha_creacion if ultimo_arqueo else datetime.combine(obtener_hora_bogota().date(), time.min)
    
    return render_template('admin/arqueo.html', fecha_inicio=fecha_inicio)

@arqueo_bp.route('/api/calcular')
@login_required
@admin_required
def calcular():
    ultimo_arqueo = ArqueoCaja.query.order_by(ArqueoCaja.fecha_creacion.desc()).first()
    fecha_inicio = ultimo_arqueo.fecha_creacion if ultimo_arqueo else datetime.combine(obtener_hora_bogota().date(), time.min)
    ahora = obtener_hora_bogota()

    # 1. Totales por Categoría (Nicho) - Ahora sumamos por CADA PRODUCTO vendido para mayor precisión
    ventas_por_nicho_raw = db.session.query(
        Category.nombre,
        func.sum(SaleDetail.cantidad_vendida * SaleDetail.precio_venta_final).label('total')
    ).select_from(SaleDetail)\
     .join(Sale, Sale.id == SaleDetail.sale_id)\
     .outerjoin(Product, Product.id == SaleDetail.product_id)\
     .outerjoin(Category, Category.id == Product.categoria_id)\
     .filter(Sale.fecha_venta >= fecha_inicio)\
     .group_by(Category.nombre).all()
    
    # Procesar para que los NULL aparezcan como "Otros / Sin Categoría" (especialmente para productos manuales)
    ventas_por_nicho = []
    for nombre, total in ventas_por_nicho_raw:
        ventas_por_nicho.append({
            "nombre": nombre if nombre else "Otros / Sin Categoría",
            "total": float(total)
        })

    # 2. Totales por Método de Pago
    totales_pago = db.session.query(
        SalePayment.metodo_pago,
        func.sum(SalePayment.monto).label('total')
    ).join(Sale, Sale.id == SalePayment.sale_id)\
     .filter(Sale.fecha_venta >= fecha_inicio)\
     .group_by(SalePayment.metodo_pago).all()

    # 3. Gastos del periodo (desde el último arqueo) - DETALLADOS
    gastos_list = Expense.query.filter(Expense.fecha >= fecha_inicio).all()
    total_gastos = sum(g.monto for g in gastos_list)

    return jsonify({
        "fecha_inicio": fecha_inicio.strftime('%Y-%m-%d %H:%M:%S'),
        "fecha_fin": ahora.strftime('%Y-%m-%d %H:%M:%S'),
        "por_nicho": ventas_por_nicho,
        "por_metodo": [{"metodo": m, "total": float(t)} for m, t in totales_pago],
        "gastos": float(total_gastos),
        "gastos_detalles": [{"categoria": g.categoria, "descripcion": g.descripcion, "monto": float(g.monto)} for g in gastos_list],
        "total_bruto": float(sum(item['total'] for item in ventas_por_nicho))
    })

@arqueo_bp.route('/confirmar', methods=['POST'])
@login_required
@admin_required
def confirmar():
    data = request.form
    ahora = obtener_hora_bogota()
    
    # Extraer totales calculados del frontend para persistir
    efectivo = float(data.get('total_efectivo', 0))
    transferencias = float(data.get('total_transferencias', 0))
    gastos = float(data.get('total_gastos', 0))
    base_inicial = float(data.get('base_inicial', 0))
    total_ventas = float(data.get('total_ventas', 0))
    
    import json
    try:
        desglose_cat = json.loads(data.get('desglose_categorias', '{}'))
        desglose_pag = json.loads(data.get('desglose_pagos', '{}'))
    except:
        desglose_cat = {}
        desglose_pag = {}
    
    nuevo_arqueo = ArqueoCaja()
    nuevo_arqueo.vendedor_id = current_user.id
    nuevo_arqueo.fecha_arqueo = ahora.date()
    nuevo_arqueo.base_inicial = base_inicial
    nuevo_arqueo.total_ventas = total_ventas
    nuevo_arqueo.gastos_del_dia = gastos
    nuevo_arqueo.total_efectivo_sistema = efectivo
    nuevo_arqueo.total_transferencia_sistema = transferencias
    nuevo_arqueo.desglose_categorias = desglose_cat
    nuevo_arqueo.desglose_pagos = desglose_pag
    nuevo_arqueo.observaciones_gastos = data.get('observaciones', 'Cierre consolidado de sistema')
    
    db.session.add(nuevo_arqueo)
    db.session.commit()
    
    flash('¡Caja cerrada con éxito! Todos los movimientos han sido consolidados.', 'success')
    return redirect(url_for('admin_bp.dashboard'))

@arqueo_bp.route('/historial')
@login_required
@admin_required
def historial():
    # Consultar todos los arqueos ordenados por fecha descendente
    cierres = ArqueoCaja.query.order_by(ArqueoCaja.fecha_creacion.desc()).all()
    return render_template('admin/arqueo_historial.html', cierres=cierres)

@arqueo_bp.route('/recibo/<int:arqueo_id>')
@login_required
@admin_required
def imprimir_recibo(arqueo_id):
    arqueo = ArqueoCaja.query.get_or_404(arqueo_id)
    return render_template('admin/arqueo_recibo.html', arqueo=arqueo)
