from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required
from models import db, Provider, Importacion, obtener_hora_bogota
from decorators import admin_required

importaciones_bp = Blueprint('importaciones_bp', __name__)

@importaciones_bp.route('/', methods=['GET'])
@login_required
@admin_required
def index():
    importaciones = Importacion.query.order_by(Importacion.fecha_registro.desc()).all()
    proveedores = Provider.query.order_by(Provider.nombre).all()
    return render_template('importaciones/index.html', importaciones=importaciones, proveedores=proveedores)

@importaciones_bp.route('/crear', methods=['POST'])
@login_required
@admin_required
def crear():
    proveedor_id = request.form.get('proveedor_id')
    numero_contenedor = request.form.get('numero_contenedor')
    valor_contenedor = float(request.form.get('valor_contenedor', 0))
    valor_flete = float(request.form.get('valor_flete', 0))
    # El toggle/checkbox llega como 'on' si está marcado, o no llega si no está marcado
    pedido_completo = request.form.get('pedido_completo') == 'on'
    observaciones = request.form.get('observaciones')

    # Validaciones de Backend
    if not proveedor_id or not numero_contenedor:
        flash('Proveedor y número de contenedor son obligatorios.', 'danger')
        return redirect(url_for('importaciones_bp.index'))

    # Regla: observaciones obligatorias si pedido_completo es False
    if not pedido_completo and (not observaciones or not observaciones.strip()):
        flash('Si el pedido no llegó completo, las observaciones son obligatorias.', 'danger')
        return redirect(url_for('importaciones_bp.index'))

    # Regla estricta: El valor_flete se guarda tal cual se ingresa, sin prorrateo.
    # El pago total es la suma (esto se maneja en el modelo/propiedad)
    
    nueva_importacion = Importacion(
        proveedor_id=proveedor_id,
        numero_contenedor=numero_contenedor.strip(),
        valor_contenedor=valor_contenedor,
        valor_flete=valor_flete,
        pedido_completo=pedido_completo,
        observaciones=observaciones.strip() if observaciones else None
    )

    db.session.add(nueva_importacion)
    db.session.commit()
    
    flash(f'Importación del contenedor #{numero_contenedor} registrada exitosamente.', 'success')
    return redirect(url_for('importaciones_bp.index'))

@importaciones_bp.route('/<int:id>', methods=['GET'])
@login_required
@admin_required
def detalle(id):
    importacion = Importacion.query.get_or_404(id)
    return jsonify({
        'id': importacion.id,
        'numero_contenedor': importacion.numero_contenedor,
        'valor_contenedor': float(importacion.valor_contenedor),
        'valor_flete': float(importacion.valor_flete),
        'pago_total': importacion.pago_total,
        'pedido_completo': importacion.pedido_completo,
        'observaciones': importacion.observaciones,
        'proveedor_id': importacion.proveedor_id,
        'proveedor_nombre': importacion.proveedor.nombre,
        'fecha': importacion.fecha_registro.strftime('%Y-%m-%d %H:%M')
    })

@importaciones_bp.route('/editar/<int:id>', methods=['POST'])
@login_required
@admin_required
def editar(id):
    importacion = Importacion.query.get_or_404(id)
    
    proveedor_id = request.form.get('proveedor_id')
    numero_contenedor = request.form.get('numero_contenedor')
    valor_contenedor = float(request.form.get('valor_contenedor', 0))
    valor_flete = float(request.form.get('valor_flete', 0))
    pedido_completo = request.form.get('pedido_completo') == 'on'
    observaciones = request.form.get('observaciones')

    if not proveedor_id or not numero_contenedor:
        flash('Proveedor y número de contenedor son obligatorios.', 'danger')
        return redirect(url_for('importaciones_bp.index'))

    if not pedido_completo and (not observaciones or not observaciones.strip()):
        flash('Si el pedido no llegó completo, las observaciones son obligatorias.', 'danger')
        return redirect(url_for('importaciones_bp.index'))

    importacion.proveedor_id = proveedor_id
    importacion.numero_contenedor = numero_contenedor.strip()
    importacion.valor_contenedor = valor_contenedor
    importacion.valor_flete = valor_flete
    importacion.pedido_completo = pedido_completo
    importacion.observaciones = observaciones.strip() if observaciones else None

    db.session.commit()
    flash(f'Importación #{numero_contenedor} actualizada correctamente.', 'success')
    return redirect(url_for('importaciones_bp.index'))
