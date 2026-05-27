from flask import Blueprint, request, jsonify, flash, redirect, render_template, url_for, session
from flask_login import login_required, current_user
from models import db, Product, ProductVariant, Sale, SaleDetail, SalePayment, Expense, Category, ProductSeries, obtener_hora_bogota, Customer
from decorators import admin_required
from decimal import Decimal
from datetime import datetime, timedelta
from sqlalchemy import or_, func
from sqlalchemy.orm import joinedload

sales_bp = Blueprint('sales_bp', __name__)



@sales_bp.route('/nueva', methods=['GET', 'POST'])
@login_required # Importante: Te bloqueará el acceso si no hay current_user logeado (Flask-Login)
def procesar_venta():
    if request.method == 'GET':
        return redirect(url_for('sales_bp.pos_visual'))

    """
    Se espera que los datos vengan en el cuerpo de la petición (JSON)
    Ej: {'items': [{ 'product_id': 1, 'cantidad': 2, 'precio_final': 15.50}, ...], 'metodo_pago': 'transferencia'}
    """
    data = request.get_json()
    items = data.get('items', [])
    pagos_data = data.get('pagos', [])
    cliente_nombre = data.get('cliente', 'Consumidor Final')
    metodo_pago_legacy = data.get('metodo_pago', 'efectivo')
    
    if not items:
        return jsonify({'error': 'No se enviaron productos para la venta'}), 400

    # Si no se envían pagos en el nuevo formato, crear uno único con el método legacy
    if not pagos_data:
        pagos_data = [{'metodo_pago': metodo_pago_legacy, 'monto': None}]  # monto=None se llenará con el total

    try:
        # Determinar el método de pago principal (para la columna legacy de retrocompatibilidad)
        if len(pagos_data) == 1:
            metodo_pago_principal = pagos_data[0].get('metodo_pago', 'efectivo')
        else:
            metodo_pago_principal = 'mixto'

        # Manejar Fecha de Venta para registros de fechas anteriores
        fecha_venta_str = data.get('fecha_venta')
        fecha_venta_obj = obtener_hora_bogota()
        if fecha_venta_str:
            try:
                fecha_seleccionada = datetime.strptime(fecha_venta_str, '%Y-%m-%d').date()
                if fecha_seleccionada != fecha_venta_obj.date():
                    # Si no es hoy, combinamos la fecha seleccionada con la hora actual para conservar secuencialidad de hora de registro
                    fecha_venta_obj = datetime.combine(fecha_seleccionada, fecha_venta_obj.time())
            except ValueError:
                pass # Fallback silencioso a la hora actual si el formato falla

        # Calcular el siguiente consecutivo
        ultimo_consecutivo = db.session.query(func.max(Sale.consecutivo)).scalar() or 0
        siguiente_consecutivo = ultimo_consecutivo + 1

        nueva_venta = Sale()
        nueva_venta.vendedor_id = current_user.id
        nueva_venta.consecutivo = siguiente_consecutivo
        nueva_venta.cliente_nombre = cliente_nombre
        nueva_venta.monto_total = Decimal('0.00')
        nueva_venta.metodo_pago = metodo_pago_principal
        nueva_venta.factura_fisica = data.get('factura_fisica')
        nueva_venta.categoria_id = session.get('categoria_actual')
        nueva_venta.fecha_venta = fecha_venta_obj
        
        # Procesar datos del cliente
        cliente_data = data.get('cliente_data')
        if cliente_data and cliente_data.get('cedula'):
            cedula = str(cliente_data.get('cedula')).strip()
            cliente = Customer.query.filter_by(cedula=cedula).first()
            if not cliente:
                cliente = Customer()
                cliente.cedula = cedula
                cliente.nombre = cliente_data.get('nombre', 'Consumidor Final')
                cliente.telefono = cliente_data.get('telefono')
                cliente.correo = cliente_data.get('correo')
                
                db.session.add(cliente)
                db.session.flush()
            else:
                # Actualizar datos si han cambiado (opcional, pero útil)
                cliente.nombre = cliente_data.get('nombre', cliente.nombre)
                cliente.telefono = cliente_data.get('telefono', cliente.telefono)
                cliente.correo = cliente_data.get('correo', cliente.correo)
            
            nueva_venta.cliente_id = cliente.id
            nueva_venta.cliente_nombre = cliente.nombre
        else:
            nueva_venta.cliente_nombre = cliente_nombre

        db.session.add(nueva_venta)
        db.session.flush()

        monto_total = Decimal('0.00')

        for item in items:
            product_id = item.get('product_id')
            variant_id = item.get('variant_id') # Posible variante
            cantidad_vendida = int(item.get('cantidad', 0))
            precio_venta_final = Decimal(str(item.get('precio_final', '0.00')))
            es_manual = item.get('es_manual', False)

            if cantidad_vendida <= 0:
                raise ValueError("La cantidad vendida debe ser mayor a 0.")

            if es_manual:
                # Producto manual (prestado de otro local) — no descuenta stock
                nombre_manual = item.get('nombre_manual', 'Producto Externo')
                precio_costo_manual = Decimal(str(item.get('precio_costo', '0.00')))

                detalle = SaleDetail()
                detalle.sale_id = nueva_venta.id
                detalle.product_id = None
                detalle.variant_id = None
                detalle.cantidad_vendida = cantidad_vendida
                detalle.precio_venta_final = precio_venta_final
                detalle.nombre_manual = nombre_manual
                detalle.precio_costo_manual = precio_costo_manual
                db.session.add(detalle)
                monto_total += (precio_venta_final * cantidad_vendida)

                # Crear el gasto automático para descontar el ingreso prestado del balance final
                if precio_costo_manual > 0:
                    gasto_externo = Expense()
                    gasto_externo.usuario_id = current_user.id
                    gasto_externo.tipo = 'Gasto Diario'
                    gasto_externo.categoria = 'Pago Prod. Externo'
                    gasto_externo.descripcion = f"Pago por producto manual prestado: {nombre_manual}"
                    gasto_externo.monto = (precio_costo_manual * cantidad_vendida)
                    gasto_externo.fecha = fecha_venta_obj
                    db.session.add(gasto_externo)
            else:
                # Producto del inventario propio
                producto = Product.query.with_for_update().get(product_id)
                
                if not producto:
                    raise ValueError(f"El producto con ID {product_id} no existe.")

                if variant_id:
                    variante = ProductVariant.query.with_for_update().get(variant_id)
                    if not variante:
                        raise ValueError(f"La variante con ID {variant_id} no existe.")
                    if cantidad_vendida > variante.cantidad_stock:
                        raise ValueError(f"Stock insuficiente para la variante '{variante.nombre_variante}' de '{producto.nombre}'. Solicitado: {cantidad_vendida}, Disponible: {variante.cantidad_stock}.")
                    variante.cantidad_stock -= cantidad_vendida
                    precio_limite_autorizado = variante.precio_costo if current_user.rol == 'admin' else variante.precio_minimo
                else:
                    if producto.es_serializado:
                        # Para productos serializados, el stock se maneja por la tabla de series
                        if cantidad_vendida > producto.cantidad_stock:
                             raise ValueError(f"Stock insuficiente de seriales para '{producto.nombre}'. Disponible: {producto.cantidad_stock}.")
                    else:
                        if cantidad_vendida > producto.cantidad_stock:
                            raise ValueError(f"Stock insuficiente para '{producto.nombre}'. Solicitado: {cantidad_vendida}, Disponible: {producto.cantidad_stock}.")
                        producto.cantidad_stock -= cantidad_vendida
                    
                    precio_limite_autorizado = producto.precio_costo if current_user.rol == 'admin' else producto.precio_minimo

                if not current_user.rol == 'admin' and precio_venta_final < precio_limite_autorizado:
                    raise ValueError(f"Precio de venta para '{producto.nombre}' está por debajo del mínimo permitido.")

                detalle = SaleDetail()
                detalle.sale_id = nueva_venta.id
                detalle.product_id = producto.id
                detalle.variant_id = variant_id
                detalle.cantidad_vendida = cantidad_vendida
                detalle.precio_venta_final = precio_venta_final
                
                # Manejo de Serial (IMEI) vinculado si viene del POS
                serial_vinculado = item.get('serial_vinculado')
                if serial_vinculado:
                    ser = ProductSeries.query.filter_by(serial=serial_vinculado, product_id=product_id, estado='disponible').first()
                    if ser:
                        ser.estado = 'vendido'
                        detalle.serial_vendido = serial_vinculado
                        # Vincular detalles técnicos capturados en el POS
                        detalle.bateria = item.get('bateria')
                        detalle.estado_producto = item.get('condicion')
                        detalle.tiempo_garantia = item.get('garantia')
                        
                        db.session.add(ser)
                        db.session.flush() # Para obtener ID del detalle
                        ser.sale_detail_id = detalle.id
                    else:
                        raise ValueError(f"El serial/IMEI '{serial_vinculado}' no está disponible o no pertenece a este producto.")
                
                db.session.add(detalle)
                monto_total += (precio_venta_final * cantidad_vendida)

        nueva_venta.monto_total = monto_total

        # Registrar los pagos mixtos en la tabla sale_payments
        total_pagos = Decimal('0.00')
        for pago_info in pagos_data:
            metodo = pago_info.get('metodo_pago', 'efectivo')
            monto_pago = pago_info.get('monto')
            
            if monto_pago is None:
                # Si solo hay un pago sin monto explícito, asignar el total completo
                monto_pago = monto_total
            else:
                monto_pago = Decimal(str(monto_pago))
            
            if monto_pago <= 0:
                raise ValueError(f"El monto del pago por '{metodo}' debe ser mayor a 0.")
            
            pago = SalePayment()
            pago.sale_id = nueva_venta.id
            pago.metodo_pago = metodo
            pago.monto = monto_pago
            db.session.add(pago)
            total_pagos += monto_pago

        # Procesar Retoma si existe en el payload
        retoma_data = data.get('retoma')
        if retoma_data:
            valor_retoma = Decimal(str(retoma_data.get('valor', '0.00')))
            if valor_retoma > 0:
                pago_retoma = SalePayment()
                pago_retoma.sale_id = nueva_venta.id
                pago_retoma.metodo_pago = 'retoma'
                pago_retoma.monto = valor_retoma
                db.session.add(pago_retoma)
                total_pagos += valor_retoma

                # Ingresar celular de retoma al inventario (Cuarentena / En Evaluación)
                imei_retoma = retoma_data.get('imei', 'N/A').strip()
                modelo_retoma = retoma_data.get('modelo', 'Retoma Genérica').strip()
                estado_inv = retoma_data.get('estado_inventario', 'En Evaluación')

                prod_retoma = Product.query.filter_by(nombre=modelo_retoma, tipo_inventario='tienda').first()
                if not prod_retoma:
                    import uuid
                    prod_retoma = Product(
                        nombre=modelo_retoma,
                        sku=f"RET-{uuid.uuid4().hex[:6].upper()}",
                        tipo_inventario='tienda',
                        es_serializado=True,
                        precio_costo=valor_retoma,
                        precio_minimo=valor_retoma,
                        precio_sugerido=valor_retoma * Decimal('1.2')
                    )
                    db.session.add(prod_retoma)
                    db.session.flush()

                if imei_retoma:
                    nueva_serie = ProductSeries(
                        product_id=prod_retoma.id,
                        serial=imei_retoma,
                        estado=estado_inv,
                        origen='retoma'
                    )
                    db.session.add(nueva_serie)

        # Validar que la suma de pagos cubra el total de la venta
        if total_pagos != monto_total:
            raise ValueError(f"La suma de los pagos (${total_pagos}) no coincide con el total de la venta (${monto_total}). Diferencia: ${monto_total - total_pagos}.")

        db.session.commit()
        
        return jsonify({
            'success': True, 
            'message': 'Venta registrada e inventario descontado con éxito.',
            'sale_id': nueva_venta.id,
            'total': str(monto_total)
        }), 201

    except ValueError as val_err:
        db.session.rollback()
        return jsonify({'error': str(val_err)}), 400
        
    except Exception:
        db.session.rollback()
        return jsonify({'error': 'Ocurrió un error interno al procesar la venta.'}), 500

@sales_bp.route('/api/clientes/buscar/<cedula>', methods=['GET'])
@login_required
def api_buscar_cliente(cedula):
    cliente = Customer.query.filter_by(cedula=cedula).first()
    if not cliente:
        return jsonify({'error': 'Cliente no encontrado'}), 404
    
    return jsonify({
        'id': cliente.id,
        'cedula': cliente.cedula,
        'nombre': cliente.nombre,
        'telefono': cliente.telefono,
        'correo': cliente.correo
    })

# Endpoint API asíncrono para el escáner del Punto de Venta
@sales_bp.route('/api/producto/<path:sku>', methods=['GET'])
@login_required
def api_buscar_producto(sku):
    # Búsqueda por SKU exacto o dentro de Atributos JSONB (IMEI, Serial, etc)

    producto = Product.query.filter(
        Product.tipo_inventario == 'tienda',
        Product.categoria_id == session.get('categoria_actual'),
        db.or_(
            Product.sku == sku,
            db.text("EXISTS (SELECT 1 FROM jsonb_each_text(products.atributos) WHERE value = :sku)").bindparams(sku=sku)
        )
    ).first()
    
    if not producto:
        return jsonify({'error': 'Código SKU o IMEI no encontrado en el sistema'}), 404
        
    # Lógica de banderas para el frontend
    seriales_disponibles = [s for s in producto.series if s.estado == 'disponible'] if producto.series else []
    tiene_seriales = len(seriales_disponibles) > 0
    es_serializado = producto.es_serializado or tiene_seriales
    requiere_imei = producto.categoria_id in [1, 6] or es_serializado

    return jsonify({
        'id': producto.id,
        'nombre': producto.nombre,
        'sku': producto.sku,
        'cantidad_stock': producto.total_stock,
        'precio_minimo': float(producto.precio_minimo),
        'precio_limite': float(producto.precio_costo) if current_user.rol == 'admin' else float(producto.precio_minimo),
        'precio_sugerido': float(producto.precio_sugerido),
        'es_serializado': es_serializado,
        'requiere_imei': requiere_imei,
        'variantes': [{"id": v.id, "nombre": v.nombre_variante, "stock": v.cantidad_stock, "precio_minimo": float(v.precio_minimo or producto.precio_minimo), "precio_limite": float(v.precio_costo or producto.precio_costo) if current_user.rol == 'admin' else float(v.precio_minimo or producto.precio_minimo), "precio_sugerido": float(v.precio_sugerido or producto.precio_sugerido)} for v in producto.variantes]
    })

# Ruta para la Impresión del formato Térmico (Ticket)
@sales_bp.route('/recibo/<int:sale_id>', methods=['GET'])
@login_required # Proteger confidencialidad del cajero
def imprimir_ticket(sale_id):
    # Regla: Retorna 404 si alguien ingresa un ID falso
    venta = Sale.query.get_or_404(sale_id)
    return render_template('sales/ticket.html', venta=venta)

# Endpoint Historial de Ventas (Administradores)
@sales_bp.route('/historial', methods=['GET'])
@login_required
@admin_required
def historial():
    # Calcular el valor exacto de 'HOY' en Bogotá
    hoy_bogota = obtener_hora_bogota().strftime('%Y-%m-%d')
    
    # Si existen los args, los usa, de lo contrario colapsa a HOY por defecto
    fecha_inicio = request.args.get('fecha_inicio', hoy_bogota)
    fecha_fin = request.args.get('fecha_fin', hoy_bogota)
    categoria_id = request.args.get('categoria_id')
    
    # Optimización: eager loading (evita N+1 con joinedload)
    query = Sale.query.options(joinedload(Sale.vendedor))
    
    # Motor de búsqueda por Rango Restricto
    if fecha_inicio:
        inicio_dt = datetime.strptime(fecha_inicio, '%Y-%m-%d')
        query = query.filter(Sale.fecha_venta >= inicio_dt)
        
    if fecha_fin:
        fin_dt = datetime.strptime(fecha_fin, '%Y-%m-%d')
        # Sumar 1 día matemáticamente para incluir los registros hasta las 23:59:59 del último día
        query = query.filter(Sale.fecha_venta < fin_dt + timedelta(days=1))

    if categoria_id:
        query = query.filter(Sale.categoria_id == categoria_id)
        
    ventas = query.order_by(Sale.fecha_venta.desc()).all()
    categorias = Category.query.all()
    
    # Auditar y cruzar sumatorios de métricas de pago
    # Sistema híbrido: usa SalePayment si existe, caso contrario cae al metodo_pago legacy
    total_efectivo = Decimal('0')
    total_nequi = Decimal('0')
    total_bancolombia = Decimal('0')
    total_daviplata = Decimal('0')
    total_tarjeta = Decimal('0')
    total_credito = Decimal('0')
    total_retoma = Decimal('0')
    total_transferencia_legacy = Decimal('0')
    total_mixto = 0  # Contador de ventas con pago mixto

    for v in ventas:
        if v.pagos:  # Pagos nuevos con tabla sale_payments
            for pago in v.pagos:
                if pago.metodo_pago == 'efectivo':
                    total_efectivo += pago.monto
                elif pago.metodo_pago == 'nequi':
                    total_nequi += pago.monto
                elif pago.metodo_pago == 'bancolombia':
                    total_bancolombia += pago.monto
                elif pago.metodo_pago == 'daviplata':
                    total_daviplata += pago.monto
                elif pago.metodo_pago == 'tarjeta':
                    total_tarjeta += pago.monto
                elif pago.metodo_pago == 'credito':
                    total_credito += pago.monto
                elif pago.metodo_pago == 'retoma':
                    total_retoma += pago.monto
                elif pago.metodo_pago == 'transferencia':
                    total_transferencia_legacy += pago.monto
            if len(v.pagos) > 1:
                total_mixto += 1
        else:  # Retrocompatibilidad con ventas antiguas sin SalePayment
            if v.metodo_pago == 'efectivo':
                total_efectivo += v.monto_total
            elif v.metodo_pago == 'nequi':
                total_nequi += v.monto_total
            elif v.metodo_pago == 'bancolombia':
                total_bancolombia += v.monto_total
            elif v.metodo_pago == 'daviplata':
                total_daviplata += v.monto_total
            elif v.metodo_pago == 'tarjeta':
                total_tarjeta += v.monto_total
            elif v.metodo_pago == 'credito':
                total_credito += v.monto_total
            elif v.metodo_pago == 'retoma':
                total_retoma += v.monto_total
            elif v.metodo_pago == 'transferencia':
                total_transferencia_legacy += v.monto_total

    # Envío al Engine de HTML
    return render_template('sales/historial.html', 
                           ventas=ventas, 
                           total_efectivo=total_efectivo,
                           total_nequi=total_nequi,
                           total_bancolombia=total_bancolombia,
                           total_daviplata=total_daviplata,
                           total_tarjeta=total_tarjeta,
                           total_credito=total_credito,
                           total_retoma=total_retoma,
                           total_transferencia_legacy=total_transferencia_legacy,
                           total_mixto=total_mixto,
                           fecha_inicio=fecha_inicio,
                           fecha_fin=fecha_fin,
                           categorias=categorias,
                           categoria_id=categoria_id)


# Endpoint para Anular/Eliminar Venta Histórica
@sales_bp.route('/eliminar/<int:sale_id>', methods=['POST'])
@login_required
@admin_required
def eliminar_venta(sale_id):
    venta = Sale.query.get_or_404(sale_id)
    
    try:
        # Revertir Stock y Series (IMEIs)
        for detalle in venta.detalles:
            if detalle.variant_id:
                variante = ProductVariant.query.with_for_update().get(detalle.variant_id)
                if variante:
                    variante.cantidad_stock += detalle.cantidad_vendida
            else:
                producto = Product.query.with_for_update().get(detalle.product_id)
                if producto:
                    # Si el producto NO es serializado, devolvemos el stock al contador estático
                    if not producto.es_serializado:
                        producto.cantidad_stock += detalle.cantidad_vendida
            
            # LIBERAR IMEI/SERIAL (Búsqueda Robusta)
            serie = None
            # 1. Intentar buscar por el ID del detalle (el vínculo más fuerte)
            serie = ProductSeries.query.filter_by(sale_detail_id=detalle.id).with_for_update().first()
            
            # 2. Si no lo encuentra, intentar por el texto del serial guardado
            if not serie and detalle.serial_vendido:
                serie = ProductSeries.query.filter_by(
                    product_id=detalle.product_id, 
                    serial=detalle.serial_vendido.strip()
                ).with_for_update().first()
            
            if serie:
                serie.estado = 'disponible'
                serie.sale_detail_id = None
                    
        # Eliminar Venta y Detalles (Cascada)
        db.session.delete(venta)
        db.session.commit()
        flash('Venta anulada: Stock devuelto e IMEIs liberados exitosamente.', 'success')
        
    except Exception:
        db.session.rollback()
        flash('Ocurrió un error al anular la venta.', 'danger')
        
    return redirect(url_for('sales_bp.historial'))

# Endpoint Catálogo Estricto de solo vista para Operarios
@sales_bp.route('/catalogo', methods=['GET'])
@login_required 
def catalogo():
    query_str = request.args.get('q', '').strip()
    
    if query_str:
        # Motor de similitud Case-Insensitive (Like)
        search_term = f"%{query_str}%"
        productos = Product.query.filter_by(tipo_inventario='tienda').filter(
            or_(
                Product.sku.ilike(search_term), 
                Product.nombre.ilike(search_term)
            )
        ).limit(50).all()
    else:
        # Límite pasivo de 50 ítems para ahorrar memoria RAM de BD en carga inicial
        productos = Product.query.filter_by(tipo_inventario='tienda').limit(50).all()
        
    return render_template('sales/catalogo.html', productos=productos, q=query_str)


# ========================================================
# ====== NUEVO MÓDULO: CAJA RÁPIDA VISUAL ======
# ========================================================
@sales_bp.route('/pos_visual', methods=['GET'])
@login_required
def pos_visual():
    # Obtener todos los productos de la tienda con relaciones cargadas
    productos = Product.query.options(
        joinedload(Product.variantes),
        joinedload(Product.series)
    ).filter_by(tipo_inventario='tienda').all()
    
    # Usar las categorías formales del modelo
    categorias_obj = Category.query.order_by(Category.nombre).all()
    categorias = [c.nombre for c in categorias_obj]
    
    # Pre-estructurar los datos para enviarlos como JSON al frontend
    productos_data = []
    for p in productos:
        cat_nombre = p.categoria.nombre if p.categoria else 'Otros'
        
        # Contar seriales disponibles reales
        seriales_disponibles = [s for s in p.series if s.estado == 'disponible'] if p.series else []
        tiene_variantes = len(p.variantes) > 0
        tiene_seriales = len(seriales_disponibles) > 0
        
        # Lógica de banderas para el frontend
        es_serializado = p.es_serializado or tiene_seriales
        requiere_imei = p.categoria_id in [1, 6] or es_serializado
        
        item = {
            'id': p.id,
            'sku': p.sku,
            'nombre': p.nombre,
            'categoria': cat_nombre,
            'precio_final': float(p.precio_sugerido),
            'precio_minimo': float(p.precio_minimo),
            'cantidad_stock': p.cantidad_stock,
            'imagen': p.imagen,
            'es_serializado': es_serializado,
            'requiere_imei': requiere_imei,
            'tiene_variantes': tiene_variantes,
            'atributos': p.atributos or {},
            'requiere_seleccion': tiene_variantes or tiene_seriales,
            'variantes': [
                {
                    'id': v.id,
                    'nombre_variante': v.nombre_variante,
                    'cantidad_stock': v.cantidad_stock,
                    'precio_minimo': float(v.precio_minimo or p.precio_minimo),
                    'precio_final': float(v.precio_sugerido or p.precio_sugerido)
                } for v in p.variantes
            ]
        }
        
        productos_data.append(item)

    return render_template('sales/pos_visual.html', categorias=categorias, productos_data=productos_data)

@sales_bp.route('/pos')
@sales_bp.route('/Pos')
@login_required
def pos_alias():
    return redirect(url_for('sales_bp.pos_visual'))

@sales_bp.route('/api/pos/buscar', methods=['GET'])
@login_required
def pos_buscar_api():
    q = request.args.get('q', '').strip()
    if not q:
        return jsonify({'tipo': 'lista', 'productos': []})
    
    tipo_inv = 'tienda'
    
    # 1. Búsqueda por SERIAL exacto disponible (Escáner de código de barras)
    serial_match = ProductSeries.query.filter_by(serial=q, estado='disponible').first()
    if serial_match:
        p = serial_match.producto
        # Para serial_exacto, devolvemos un objeto específico para agregarlo directo al carrito
        return jsonify({
            'tipo': 'serial_exacto',
            'producto': {
                'id': p.id,
                'sku': p.sku,
                'nombre': p.nombre,
                'precio_final': float(p.precio_sugerido),
                'precio_minimo': float(p.precio_minimo),
                'serial_vinculado': serial_match.serial,
                'serie_id': serial_match.id,
                'es_serializado': True,
                'requiere_imei': True # Siempre abre el modal de detalles (batería, etc)
            }
        })

    # 2. Búsqueda normal por Nombre o SKU
    search_term = f"%{q}%"
    productos = Product.query.filter(
        Product.tipo_inventario == tipo_inv,
        db.or_(
            Product.nombre.ilike(search_term),
            Product.sku.ilike(search_term),
            db.text("EXISTS (SELECT 1 FROM jsonb_each_text(products.atributos) WHERE value ILIKE :q)").bindparams(q=search_term)
        )
    ).limit(20).all()

    resultados = []
    for p in productos:
        cat_nombre = p.categoria.nombre if p.categoria else 'Otros'
        
        # Contar seriales disponibles reales
        seriales_disponibles = [s for s in p.series if s.estado == 'disponible'] if p.series else []
        tiene_seriales = len(seriales_disponibles) > 0
        tiene_variantes = len(p.variantes) > 0
        
        # Lógica estricta de banderas para el Modal
        es_serializado = p.es_serializado or tiene_seriales
        requiere_imei = p.categoria_id in [1, 6] or es_serializado
        
        resultados.append({
            'id': p.id,
            'sku': p.sku,
            'nombre': p.nombre,
            'categoria': cat_nombre,
            'precio_final': float(p.precio_sugerido),
            'precio_minimo': float(p.precio_minimo),
            'cantidad_stock': p.cantidad_stock,
            'imagen': p.imagen or 'default_product.png',
            'requiere_imei': requiere_imei,
            'tiene_variantes': tiene_variantes,
            'es_serializado': es_serializado,
            'atributos': p.atributos or {},
            'variantes': [
                {
                    'id': v.id,
                    'nombre_variante': v.nombre_variante,
                    'cantidad_stock': v.cantidad_stock,
                    'precio_minimo': float(v.precio_minimo or p.precio_minimo),
                    'precio_final': float(v.precio_sugerido or p.precio_sugerido)
                } for v in p.variantes
            ]
        })

    return jsonify({
        'tipo': 'lista',
        'productos': resultados
    })

# ========================================================
# ====== API ENDPOINTS (DESACTIVADOS PARA ESQUELETO) ======
# ========================================================

@sales_bp.route('/api/search-invoices')
@sales_bp.route('/api/invoice-details/<int:id>')
@sales_bp.route('/api/search-stock')
@sales_bp.route('/api/process-exchange', methods=['POST'])
@sales_bp.route('/api/exchanges-history')
@login_required
def sales_modulo_desactivado(*args, **kwargs):
    return jsonify({'error': 'Este módulo no está disponible en la versión simplificada.'}), 403


