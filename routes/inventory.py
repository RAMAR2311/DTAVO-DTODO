from decimal import Decimal
import os
from sqlalchemy import func
from werkzeug.utils import secure_filename
from flask import current_app, Blueprint, render_template, request, redirect, url_for, flash, abort, send_file, jsonify, session
from flask_login import login_required, current_user
from models import db, Product, StockAdjustment, ProductVariant, Category, ProductSeries, obtener_hora_bogota
from decorators import admin_or_bodega_required, inventory_access_required
import pandas as pd
from io import BytesIO

inventory_bp = Blueprint('inventory_bp', __name__)

MAX_PRICE_LIMIT = 99999999999.99

def validate_prices(*prices):
    """Retorna True si todos los precios están dentro del rango permitido por la DB."""
    for price in prices:
        if price > MAX_PRICE_LIMIT:
            return False
    return True

def limpiar_celulares_sin_stock():
    """Elimina automáticamente productos serializados sin stock ni IMEIs disponibles."""
    try:
        prods_serializados = Product.query.filter_by(es_serializado=True).all()
        hubo_cambios = False
        for p in prods_serializados:
            cant_disp = ProductSeries.query.filter_by(product_id=p.id, estado='disponible').count()
            if cant_disp == 0:
                try:
                    db.session.delete(p)
                    db.session.flush()
                    hubo_cambios = True
                except Exception:
                    db.session.rollback()
        if hubo_cambios:
            db.session.commit()
    except Exception:
        db.session.rollback()

@inventory_bp.route('/', methods=['GET'])
@login_required
@inventory_access_required
def index():
    limpiar_celulares_sin_stock()
    cat_id = session.get('categoria_actual')
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    titulo_contexto = "Inventario Unificado"
    
    query = Product.query.filter_by(tipo_inventario=tipo)
    
    if cat_id:
        categoria = Category.query.get(cat_id)
        if categoria:
            titulo_contexto = f"Nicho: {categoria.nombre}"
            query = query.filter_by(categoria_id=cat_id)
            
    import math

    page = request.args.get('page', 1, type=int)
    per_page = 30

    raw_productos = query.order_by(Product.id.desc()).all()
    # Ocultar productos serializados que hayan quedado con 0 IMEIs
    all_productos = []
    for p in raw_productos:
        if p.es_serializado and p.cantidad_stock == 0:
            continue
        all_productos.append(p)
    
    total_unidades = 0
    total_costo = 0.0
    total_potencial = 0.0
    
    for p in all_productos:
        # Usamos la propiedad dinámica del modelo que ya cuenta IMEIs disponibles
        stock_actual = p.cantidad_stock

        if p.variantes:
            for v in p.variantes:
                v_stock = v.cantidad_stock
                total_unidades += v_stock
                total_costo += (v_stock * float(v.precio_costo or p.precio_costo))
                total_potencial += (v_stock * float(v.precio_sugerido or p.precio_sugerido))
        else:
            total_unidades += stock_actual
            total_costo += (stock_actual * float(p.precio_costo))
            total_potencial += (stock_actual * float(p.precio_sugerido))

    # Paginación de 30 ítems por página
    total_items = len(all_productos)
    total_pages = math.ceil(total_items / per_page) if total_items > 0 else 1
    if page < 1: page = 1
    if page > total_pages: page = total_pages

    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page
    productos_pagina = all_productos[start_idx:end_idx]
            
    return render_template('inventory/index.html', 
                           productos=productos_pagina, 
                           total_unidades=total_unidades, 
                           total_costo=total_costo, 
                           total_potencial=total_potencial,
                           titulo_contexto=titulo_contexto,
                           page=page,
                           total_pages=total_pages,
                           total_items=total_items,
                           per_page=per_page)

@inventory_bp.route('/nuevo', methods=['GET', 'POST'])
@login_required
@inventory_access_required
def nuevo():
    categorias = Category.query.order_by(Category.nombre).all()
    if request.method == 'POST':
        # --- Manejo de Imagen ---
        imagen_filename = None
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                # Directorio dinámico según la marca actual o por defecto
                static_path = os.path.join(current_app.root_path, 'static', 'uploads')
                if not os.path.exists(static_path):
                    os.makedirs(static_path)
                file.save(os.path.join(static_path, filename))
                imagen_filename = filename

        # Precios
        nuevo_costo = float(request.form.get('precio_costo', '0').replace(',', ''))
        nuevo_minimo = float(request.form.get('precio_minimo', '0').replace(',', ''))
        nuevo_sugerido = float(request.form.get('precio_sugerido', '0').replace(',', ''))

        if not validate_prices(nuevo_costo, nuevo_minimo, nuevo_sugerido):
            flash('Uno de los precios ingresados es demasiado alto.', 'danger')
            return render_template('inventory/form.html', categorias=categorias)

        # Atributos Dinámicos (JSONB)
        attr_keys = request.form.getlist('attr_key[]')
        attr_values = request.form.getlist('attr_value[]')
        atributos_dict = {}
        for k, v in zip(attr_keys, attr_values):
            if k.strip():
                atributos_dict[k.strip()] = v.strip()

        stock_min_alerta = request.form.get('stock_minimo_alerta')
        if stock_min_alerta is not None and stock_min_alerta.strip() != '':
            try:
                atributos_dict['stock_minimo_alerta'] = int(stock_min_alerta.strip())
            except ValueError:
                atributos_dict['stock_minimo_alerta'] = 3

        # Verificar si el SKU ya existía previamente en el sistema (por historial o stock 0)
        nuevo_sku = request.form.get('sku').strip()
        existente = Product.query.filter_by(sku=nuevo_sku).first()

        if existente:
            nuevo_p = existente
            is_reactivation = True
        else:
            nuevo_p = Product()
            nuevo_p.sku = nuevo_sku
            is_reactivation = False

        nuevo_p.nombre = request.form.get('nombre').strip()
        nuevo_p.tipo_inventario = 'bodega' if current_user.rol == 'bodega' else 'tienda'
        cat_id = request.form.get('categoria_id')
        nuevo_p.categoria_id = int(cat_id) if cat_id else None
        nuevo_p.es_serializado = request.form.get('es_serializado') == 'on'
        nuevo_p.precio_costo = nuevo_costo
        nuevo_p.precio_minimo = nuevo_minimo
        nuevo_p.precio_sugerido = nuevo_sugerido
        if imagen_filename:
            nuevo_p.imagen = imagen_filename
        nuevo_p.observacion = request.form.get('observacion')
        
        stock_ingresado = int(request.form.get('cantidad_stock', 0))
        if not nuevo_p.es_serializado:
            if is_reactivation:
                nuevo_p.cantidad_stock = (nuevo_p.cantidad_stock or 0) + stock_ingresado
            else:
                nuevo_p.cantidad_stock = stock_ingresado
        
        try:
            if not is_reactivation:
                db.session.add(nuevo_p)
            db.session.flush()
            
            # Kardex inicial o de reabastecimiento
            ajuste = StockAdjustment()
            ajuste.product_id = nuevo_p.id
            ajuste.admin_id = current_user.id
            ajuste.tipo_movimiento = 'Reabastecimiento SKU' if is_reactivation else 'Creación Inicial'
            ajuste.stock_anterior = 0 if not is_reactivation else (nuevo_p.cantidad_stock - stock_ingresado)
            ajuste.stock_nuevo = nuevo_p.cantidad_stock
            db.session.add(ajuste)
            
            # --- Procesar IMEIs / Seriales si es serializado ---
            if nuevo_p.es_serializado:
                imeis_list = request.form.getlist('imeis[]')
                for imei_str in imeis_list:
                    clean_imei = imei_str.strip()
                    if clean_imei:
                        exist_s = ProductSeries.query.filter_by(product_id=nuevo_p.id, serial=clean_imei).first()
                        if not exist_s:
                            s = ProductSeries()
                            s.product_id = nuevo_p.id
                            s.serial = clean_imei
                            s.estado = 'disponible'
                            s.origen = 'sistema'
                            db.session.add(s)

            # --- Procesar Variantes desde el Formulario ---
            var_names = request.form.getlist('variant_name[]')
            var_stocks = request.form.getlist('variant_stock[]')
            var_entrantes = request.form.getlist('variant_stock_entrante[]')
            
            for idx, (v_name, v_stock) in enumerate(zip(var_names, var_stocks)):
                if v_name.strip():
                    stock_base = int(v_stock or 0)
                    stock_ent = int(var_entrantes[idx] or 0) if idx < len(var_entrantes) else 0
                    nueva_v = ProductVariant()
                    nueva_v.product_id = nuevo_p.id
                    nueva_v.nombre_variante = v_name.strip()
                    nueva_v.cantidad_stock = stock_base + stock_ent
                    nueva_v.precio_costo = nuevo_p.precio_costo
                    nueva_v.precio_minimo = nuevo_p.precio_minimo
                    nueva_v.precio_sugerido = nuevo_p.precio_sugerido
                    db.session.add(nueva_v)
            
            db.session.commit()

            if is_reactivation:
                flash(f"El producto '{nuevo_p.nombre}' (SKU: {nuevo_p.sku}) ya existía en el catálogo y ha sido reabastecido y reactivado exitosamente con el nuevo stock e IMEIs.", 'success')
            else:
                flash('Producto creado exitosamente.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al guardar producto: {str(e)}', 'danger')
            
    return render_template('inventory/form.html', categorias=categorias)

@inventory_bp.route('/editar/<int:id>', methods=['GET', 'POST'])
@login_required
@inventory_access_required
def editar_producto(id):
    producto = Product.query.get_or_404(id)
    categorias = Category.query.order_by(Category.nombre).all()
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    if producto.tipo_inventario != tipo:
        abort(403)
    
    if request.method == 'POST':
        stock_anterior = producto.cantidad_stock
        cantidad_base = int(request.form.get('cantidad_stock', 0))
        stock_entrante = int(request.form.get('stock_entrante', '0') or 0)
        cantidad_stock_nueva = cantidad_base + stock_entrante
        
        if 'imagen' in request.files:
            file = request.files['imagen']
            if file and file.filename != '':
                filename = secure_filename(file.filename)
                static_path = os.path.join(current_app.root_path, 'static', 'uploads')
                file.save(os.path.join(static_path, filename))
                producto.imagen = filename
                
        if current_user.rol == 'admin':
            nuevo_costo = float(request.form.get('precio_costo', '0').replace(',', ''))
            nuevo_minimo = float(request.form.get('precio_minimo', '0').replace(',', ''))
            nuevo_sugerido = float(request.form.get('precio_sugerido', '0').replace(',', ''))
        else:
            nuevo_costo = float(producto.precio_costo or 0)
            nuevo_minimo = float(producto.precio_minimo or 0)
            nuevo_sugerido = float(producto.precio_sugerido or 0)

        if not validate_prices(nuevo_costo, nuevo_minimo, nuevo_sugerido):
            flash('Precios exceden el límite permitido.', 'danger')
            return render_template('inventory/form.html', producto=producto, categorias=categorias)

        # Atributos Dinámicos
        attr_keys = request.form.getlist('attr_key[]')
        attr_values = request.form.getlist('attr_value[]')
        atributos_dict = {}
        for k, v in zip(attr_keys, attr_values):
            if k.strip():
                atributos_dict[k.strip()] = v.strip()

        stock_min_alerta = request.form.get('stock_minimo_alerta')
        if stock_min_alerta is not None and stock_min_alerta.strip() != '':
            try:
                atributos_dict['stock_minimo_alerta'] = int(stock_min_alerta.strip())
            except ValueError:
                atributos_dict['stock_minimo_alerta'] = 3

        nuevo_sku = request.form.get('sku').strip()
        if nuevo_sku != producto.sku:
            existente = Product.query.filter_by(sku=nuevo_sku).first()
            if existente:
                flash(f"Error: El código SKU '{nuevo_sku}' ya está en uso por otro producto ({existente.nombre}). Por favor ingresa uno diferente.", 'danger')
                return render_template('inventory/form.html', producto=producto, categorias=categorias)

        producto.sku = nuevo_sku
        producto.nombre = request.form.get('nombre').strip()
        producto.cantidad_stock = cantidad_stock_nueva
        producto.precio_costo = nuevo_costo
        producto.precio_minimo = nuevo_minimo
        producto.precio_sugerido = nuevo_sugerido
        producto.categoria_id = request.form.get('categoria_id')
        producto.es_serializado = request.form.get('es_serializado') == 'on'
        producto.atributos = atributos_dict
        producto.observacion = request.form.get('observacion')


        # Propagar precios a variantes
        for var in producto.variantes:
            var.precio_costo = nuevo_costo
            var.precio_minimo = nuevo_minimo
            var.precio_sugerido = nuevo_sugerido
        
        try:
            if stock_anterior != cantidad_stock_nueva:
                ajuste = StockAdjustment()
                ajuste.product_id = producto.id
                ajuste.admin_id = current_user.id
                ajuste.tipo_movimiento = 'Ajuste Manual'
                ajuste.stock_anterior = stock_anterior
                ajuste.stock_nuevo = cantidad_stock_nueva
                db.session.add(ajuste)

            # Sincronizar IMEIs/Seriales si es producto serializado
            if producto.es_serializado:
                imeis_form = [i.strip() for i in request.form.getlist('imeis[]') if i.strip()]
                seriales_db = ProductSeries.query.filter_by(product_id=producto.id).all()
                dict_db = {s.serial: s for s in seriales_db}

                # 1. Agregar nuevos IMEIs
                for imei in imeis_form:
                    if imei not in dict_db:
                        new_s = ProductSeries()
                        new_s.product_id = producto.id
                        new_s.serial = imei
                        new_s.estado = 'disponible'
                        new_s.origen = 'sistema'
                        db.session.add(new_s)

                # 2. Eliminar IMEIs retirados de la lista (solo si están disponibles)
                for imei, s_obj in dict_db.items():
                    if imei not in imeis_form and s_obj.estado == 'disponible':
                        db.session.delete(s_obj)
            var_names = request.form.getlist('variant_name[]')
            var_stocks = request.form.getlist('variant_stock[]')
            var_entrantes = request.form.getlist('variant_stock_entrante[]')
            
            if var_names:
                # 1. Obtener variantes actuales
                variantes_actuales = {v.nombre_variante: v for v in producto.variantes}
                nombres_en_form = set()
                
                for idx, (v_name, v_stock) in enumerate(zip(var_names, var_stocks)):
                    name = v_name.strip()
                    if not name: continue
                    nombres_en_form.add(name)
                    stock_base = int(v_stock or 0)
                    stock_ent = int(var_entrantes[idx] or 0) if idx < len(var_entrantes) else 0
                    stock_final = stock_base + stock_ent
                    
                    if name in variantes_actuales:
                        # Actualizar
                        variantes_actuales[name].cantidad_stock = stock_final
                    else:
                        # Crear
                        nueva_v = ProductVariant()
                        nueva_v.product_id = producto.id
                        nueva_v.nombre_variante = name
                        nueva_v.cantidad_stock = stock_final
                        nueva_v.precio_costo = producto.precio_costo
                        nueva_v.precio_minimo = producto.precio_minimo
                        nueva_v.precio_sugerido = producto.precio_sugerido
                        db.session.add(nueva_v)
                
                # 2. Opcional: Eliminar las que no están en el form (y no tienen ventas)
                for name, v_obj in variantes_actuales.items():
                    if name not in nombres_en_form:
                        # Solo eliminamos si no tiene ventas para evitar errores de integridad
                        from models import SaleDetail
                        if not SaleDetail.query.filter_by(variant_id=v_obj.id).first():
                            db.session.delete(v_obj)

            db.session.commit()
            flash('Producto actualizado correctamente.', 'success')
            return redirect(url_for('inventory_bp.index'))
        except Exception as e:
            db.session.rollback()
            flash(f'Error al actualizar: {str(e)}', 'danger')

    return render_template('inventory/form.html', producto=producto, categorias=categorias)

@inventory_bp.route('/historial-ajustes')
@login_required
@inventory_access_required
def historial_ajustes():
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    ajustes = StockAdjustment.query.join(Product).filter(Product.tipo_inventario == tipo).order_by(StockAdjustment.fecha_ajuste.desc()).all()
    return render_template('inventory/historial_ajustes.html', ajustes=ajustes)

@inventory_bp.route('/ver/<int:id>', methods=['GET'])
@login_required
@inventory_access_required
def ver_producto(id):
    producto = Product.query.get_or_404(id)
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    if producto.tipo_inventario != tipo:
        abort(403)
        
    # 1. Obtener ajustes registrados en la BD (StockAdjustment)
    db_ajustes = StockAdjustment.query.filter_by(product_id=id).all()
    
    movimientos = []
    sub_ticket_ids = set()
    
    for aj in db_ajustes:
        diff = aj.stock_nuevo - aj.stock_anterior
        nombre_user = aj.admin.nombre if aj.admin else 'Sistema'
        movimientos.append({
            'fecha_ajuste': aj.fecha_ajuste,
            'usuario_nombre': nombre_user,
            'tipo_movimiento': aj.tipo_movimiento,
            'stock_anterior': aj.stock_anterior,
            'stock_nuevo': aj.stock_nuevo,
            'diferencia': diff
        })
        if aj.tipo_movimiento and 'Venta Ticket #' in aj.tipo_movimiento:
            try:
                t_id = aj.tipo_movimiento.split('Venta Ticket #')[1].split(' ')[0]
                sub_ticket_ids.add(int(t_id))
            except (IndexError, ValueError):
                pass

    # 2. Consultar ventas históricas en SaleDetail que no estén registradas en StockAdjustment
    from models import SaleDetail, Sale
    sales_details = (SaleDetail.query.join(Sale)
                     .filter(SaleDetail.product_id == id)
                     .order_by(Sale.fecha_venta.desc()).all())

    for sd in sales_details:
        if sd.sale and sd.sale.id not in sub_ticket_ids:
            variant_str = f" ({sd.variante.nombre_variante})" if sd.variante else ""
            imei_str = f" - IMEI: {sd.serial_vendido}" if sd.serial_vendido else ""
            tipo_str = f"Venta Ticket #{sd.sale.id}{variant_str}{imei_str}"
            
            vendedor_nombre = sd.sale.vendedor.nombre if (sd.sale and sd.sale.vendedor) else 'Vendedor'
            
            movimientos.append({
                'fecha_ajuste': sd.sale.fecha_venta,
                'usuario_nombre': vendedor_nombre,
                'tipo_movimiento': tipo_str,
                'stock_anterior': '-',
                'stock_nuevo': '-',
                'diferencia': -sd.cantidad_vendida
            })
            sub_ticket_ids.add(sd.sale.id)

    from datetime import datetime
    movimientos.sort(key=lambda x: x['fecha_ajuste'] if x['fecha_ajuste'] else datetime.min, reverse=True)

    return render_template('inventory/ver.html', producto=producto, ajustes=movimientos)

@inventory_bp.route('/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_or_bodega_required
def eliminar_producto(id):
    producto = Product.query.get_or_404(id)
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    
    if producto.tipo_inventario != tipo:
        abort(403)
        
    from models import SaleDetail, Maneo, FacturaBodegaDetalle
    
    # 1. Validación de seguridad en cascada (No eliminar lo que tiene historia financiera/logística)
    if SaleDetail.query.filter_by(product_id=producto.id).first():
        flash('Acción denegada: El producto ya está vinculado a Historial de Ventas. Sugerencia: Ajustar stock a 0.', 'warning')
        return redirect(url_for('inventory_bp.index'))
        
    if Maneo.query.filter_by(product_id=producto.id).first():
        flash('Acción denegada: El producto tiene registros históticos en Maneos (Préstamos).', 'warning')
        return redirect(url_for('inventory_bp.index'))
        
    if FacturaBodegaDetalle.query.filter_by(producto_id=producto.id).first():
        flash('Acción denegada: El producto forma parte del detalle de una Factura Asignada.', 'warning')
        return redirect(url_for('inventory_bp.index'))
        
    try:
        # 2. Purgar dependencias suaves (Ajustes de Kardex)
        for ajuste in producto.ajustes_stock:
            db.session.delete(ajuste)
            
        # 3. Eliminar el producto madre (las Variantes se van automáticamente por regla delete-orphan de SQLAlchemy)
        nombre = producto.nombre
        db.session.delete(producto)
        db.session.commit()
        flash(f'Producto "{nombre}" fue borrado permanentemente del inventario.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error bloqueante en la base de datos: {str(e)}', 'danger')
        
    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/producto/<int:id>/agregar_variante', methods=['POST'])
@login_required
@inventory_access_required
def agregar_variante(id):
    producto = Product.query.get_or_404(id)
    nombre_variante = request.form.get('nombre_variante')
    cantidad_stock = int(request.form.get('cantidad_stock', 0))
    
    precio_costo_req = request.form.get('precio_costo')
    precio_minimo_req = request.form.get('precio_minimo')
    precio_sugerido_req = request.form.get('precio_sugerido')

    if not nombre_variante:
        flash('El nombre de la variante es obligatorio.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    if current_user.rol == 'admin':
        v_costo = float(str(precio_costo_req).replace(',', '')) if precio_costo_req else float(producto.precio_costo or 0)
        v_minimo = float(str(precio_minimo_req).replace(',', '')) if precio_minimo_req else float(producto.precio_minimo or 0)
        v_sugerido = float(str(precio_sugerido_req).replace(',', '')) if precio_sugerido_req else float(producto.precio_sugerido or 0)
    else:
        v_costo = float(producto.precio_costo or 0)
        v_minimo = float(producto.precio_minimo or 0)
        v_sugerido = float(producto.precio_sugerido or 0)

    if not validate_prices(v_costo, v_minimo, v_sugerido):
        flash('Uno de los precios para la variante es demasiado alto.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    # Se crea la variante con asignación explícita
    nueva_v = ProductVariant()
    nueva_v.product_id = producto.id
    nueva_v.nombre_variante = nombre_variante
    nueva_v.cantidad_stock = cantidad_stock
    nueva_v.precio_costo = v_costo
    nueva_v.precio_minimo = v_minimo
    nueva_v.precio_sugerido = v_sugerido

    try:
        db.session.add(nueva_v)
        if cantidad_stock > 0:
            ajuste = StockAdjustment(
                product_id=producto.id,
                admin_id=current_user.id,
                tipo_movimiento=f"Creación Variante '{nombre_variante}'",
                stock_anterior=0,
                stock_nuevo=cantidad_stock,
                fecha_ajuste=obtener_hora_bogota()
            )
            db.session.add(ajuste)
        db.session.commit()
        flash(f'Variante "{nombre_variante}" agregada con éxito.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al agregar la variante.', 'danger')

    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/variante/<int:id>/editar', methods=['POST'])
@login_required
@inventory_access_required
def editar_variante(id):
    variante = ProductVariant.query.get_or_404(id)
    
    nuevo_stock = int(request.form.get('cantidad_stock', variante.cantidad_stock))
    stock_anterior = variante.cantidad_stock
    
    variante.nombre_variante = request.form.get('nombre_variante')
    
    precio_costo_req = request.form.get('precio_costo')
    precio_minimo_req = request.form.get('precio_minimo')
    precio_sugerido_req = request.form.get('precio_sugerido')
    
    if current_user.rol == 'admin':
        v_costo = float(str(precio_costo_req).replace(',', '')) if precio_costo_req else float(variante.precio_costo or 0)
        v_minimo = float(str(precio_minimo_req).replace(',', '')) if precio_minimo_req else float(variante.precio_minimo or 0)
        v_sugerido = float(str(precio_sugerido_req).replace(',', '')) if precio_sugerido_req else float(variante.precio_sugerido or 0)
    else:
        v_costo = float(variante.precio_costo or 0)
        v_minimo = float(variante.precio_minimo or 0)
        v_sugerido = float(variante.precio_sugerido or 0)

    if not validate_prices(v_costo, v_minimo, v_sugerido):
        flash('Uno de los precios para la variante es demasiado alto.', 'danger')
        return redirect(url_for('inventory_bp.index'))

    if stock_anterior != nuevo_stock:
        ajuste = StockAdjustment(
            product_id=variante.product_id,
            admin_id=current_user.id,
            tipo_movimiento=f"Ajuste Variante '{variante.nombre_variante}'",
            stock_anterior=stock_anterior,
            stock_nuevo=nuevo_stock,
            fecha_ajuste=obtener_hora_bogota()
        )
        db.session.add(ajuste)

    variante.cantidad_stock = nuevo_stock
    variante.precio_costo = v_costo
    variante.precio_minimo = v_minimo
    variante.precio_sugerido = v_sugerido
    
    try:
        db.session.commit()
        flash('Variante editada con éxito.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al editar la variante.', 'danger')
        
    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/variante/<int:id>/eliminar', methods=['POST'])
@login_required
@admin_or_bodega_required
def eliminar_variante(id):
    variante = ProductVariant.query.get_or_404(id)
    
    from models import SaleDetail
    # Validar si ya hay ventas facturadas con esta variante para evitar conflictos en el Balance Financiero
    if SaleDetail.query.filter_by(variant_id=variante.id).first():
        flash('Acción denegada: No se puede eliminar una variante que tiene ventas facturadas (por integridad financiera). Sugerencia: Actualiza su stock a 0.', 'warning')
        return redirect(url_for('inventory_bp.index'))
        
    try:
        nombre = variante.nombre_variante
        db.session.delete(variante)
        db.session.commit()
        flash(f'La subcategoría "{nombre}" fue borrada exitosamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error grave en servidor al eliminar la variante: {str(e)}', 'danger')
        
    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/plantilla-importacion')
@login_required
@inventory_access_required
def descargar_plantilla():
    # Crear la estructura de datos incluyendo la casilla de nicho
    cols = ['sku', 'nombre', 'nicho', 'subcategoria', 'cantidad_stock', 'precio_costo', 'precio_minimo', 'precio_sugerido', 'observacion']
    df = pd.DataFrame(columns=cols)
    
    # Filas de ejemplo instructivas
    df.loc[0] = ['SKU-001', 'Camiseta Polo', 'Ropa', 'Azul / M', 50, 15000, 25000, 35000, 'Algodón Premium']
    df.loc[1] = ['SKU-001', 'Camiseta Polo', 'Ropa', 'Rojo / L', 30, 15000, 25000, 35000, 'Algodón Premium']
    df.loc[2] = ['SKU-002', 'Protector Pantalla G7', 'Accesorios', '', 100, 2000, 5000, 8000, 'Sin subcategorías']
    
    output = BytesIO()
    
    # Usar XlsxWriter como motor para aplicar estilos profesionales
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        df.to_excel(writer, index=False, sheet_name='Plantilla Dtavo')
        
        workbook  = writer.book
        worksheet = writer.sheets['Plantilla Dtavo']
        
        # Formato para el encabezado (Dorado Dtavo)
        header_format = workbook.add_format({
            'bold': True,
            'text_wrap': True,
            'valign': 'vcenter',
            'align': 'center',
            'fg_color': '#DDB856',
            'font_color': '#1A1818',
            'border': 1
        })
        
        # Aplicar formato a los encabezados
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(0, col_num, value, header_format)
            # Auto-ajustar ancho de columna (basado en el largo del texto del header o ejemplo)
            column_len = max(len(str(value)), 15)
            worksheet.set_column(col_num, col_num, column_len)

    output.seek(0)
    return send_file(output, download_name="plantilla_importacion_dtavo.xlsx", as_attachment=True)

@inventory_bp.route('/importar', methods=['POST'])
@login_required
@inventory_access_required
def importar_inventario():
    if 'archivo' not in request.files:
        flash('No se seleccionó ningún archivo.', 'danger')
        return redirect(url_for('inventory_bp.index'))
        
    archivo = request.files['archivo']
    if archivo.filename == '':
        flash('Ningún archivo seleccionado.', 'danger')
        return redirect(url_for('inventory_bp.index'))
        
    if not (archivo.filename.endswith('.xlsx') or archivo.filename.endswith('.csv')):
        flash('Formato no válido. Solo debes subir archivos .xlsx o .csv', 'warning')
        return redirect(url_for('inventory_bp.index'))
        
    try:
        # Lectura con pandas según la extensión
        if archivo.filename.endswith('.csv'):
            df = pd.read_csv(archivo)
        else:
            df = pd.read_excel(archivo)
            
        required_cols = ['sku', 'nombre', 'cantidad_stock', 'precio_costo', 'precio_minimo', 'precio_sugerido', 'observacion']
        # 'nicho' / 'categoria' y 'subcategoria' son opcionales pero las procesamos dinámicamente
        
        # Limpieza de encabezados para evitar problemas por mayúsculas o espacios accidentales
        df.columns = [str(c).strip().lower() for c in df.columns]
        
        missing = [c for c in required_cols if c not in df.columns]
        if missing:
            flash(f"El archivo fue rechazado. Faltan las siguientes columnas: {', '.join(missing)}", 'danger')
            return redirect(url_for('inventory_bp.index'))
            
        tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
        creados = 0
        actualizados = 0
        variantes_procesadas = 0
        
        for idx, row in df.iterrows():
            sku = row['sku']
            nombre = row['nombre']
            stock = row['cantidad_stock']
            costo = row['precio_costo']
            minimo = row['precio_minimo']
            sugerido = row['precio_sugerido']
            obs = row['observacion']

            sku_raw = str(sku).strip()
            if not sku_raw or sku_raw.lower() == 'nan':
                continue
            
            # Limpiar cantidades para evitar errores NaN o Nulls
            cant = int(stock) if pd.notna(stock) else 0
            
            nombre_val = str(nombre).strip()
            obs_val = str(obs).strip() if pd.notna(obs) else ''
            if obs_val.lower() == 'nan':
                obs_val = ''

            # Procesamiento de Nicho / Categoría desde el Excel
            nicho_val = ''
            if 'nicho' in row and pd.notna(row['nicho']):
                nicho_val = str(row['nicho']).strip()
            elif 'categoria' in row and pd.notna(row['categoria']):
                nicho_val = str(row['categoria']).strip()

            categoria_id_asignar = None
            if nicho_val and nicho_val.lower() not in ['nan', 'none', '']:
                cat_match = Category.query.filter(func.lower(Category.nombre) == func.lower(nicho_val)).first()
                if not cat_match:
                    cat_match = Category(nombre=nicho_val.strip().title())
                    db.session.add(cat_match)
                    db.session.flush()
                categoria_id_asignar = cat_match.id

            sub_raw = str(row['subcategoria']).strip() if 'subcategoria' in row else ''
            if sub_raw.lower() in ['nan', 'none', '']:
                sub_raw = None

            prod = Product.query.filter_by(sku=sku_raw, tipo_inventario=tipo).first()
            
            if not prod:
                # CREAR PRODUCTO BASE PRIMERO
                nuevo_p = Product()
                nuevo_p.sku = str(sku_raw)
                nuevo_p.nombre = str(nombre_val)
                nuevo_p.tipo_inventario = tipo
                nuevo_p.cantidad_stock = 0
                nuevo_p.precio_costo = Decimal(str(costo))
                nuevo_p.precio_minimo = Decimal(str(minimo))
                nuevo_p.precio_sugerido = Decimal(str(sugerido))
                nuevo_p.observacion = obs_val
                if categoria_id_asignar:
                    nuevo_p.categoria_id = categoria_id_asignar
                db.session.add(nuevo_p)
                db.session.flush()
                creados += 1
                prod = nuevo_p
            else:
                # Actualizar información general del producto existente
                prod.nombre = nombre_val
                prod.observacion = obs_val
                if categoria_id_asignar:
                    prod.categoria_id = categoria_id_asignar

                if not sub_raw: # Si es producto base, actualizamos precios y PROPAGAMOS a variantes
                    prod.precio_costo = Decimal(str(costo))
                    prod.precio_minimo = Decimal(str(minimo))
                    prod.precio_sugerido = Decimal(str(sugerido))
                    
                    # Sincronizar variantes existentes con los nuevos precios del Excel
                    for var in prod.variantes:
                        var.precio_costo = Decimal(str(costo))
                        var.precio_minimo = Decimal(str(minimo))
                        var.precio_sugerido = Decimal(str(sugerido))
                actualizados += 1

            if sub_raw:
                # PROCESAR COMO VARIANTE
                var = ProductVariant.query.filter_by(product_id=prod.id, nombre_variante=sub_raw).first()
                if var:
                    stock_ant = var.cantidad_stock
                    var.cantidad_stock += cant
                    # Actualizar precios específicos de la variante si vienen en el excel
                    var.precio_costo = Decimal(str(costo))
                    var.precio_minimo = Decimal(str(minimo))
                    var.precio_sugerido = Decimal(str(sugerido))
                else:
                    stock_ant = 0
                    var = ProductVariant()
                    var.product_id = prod.id
                    var.nombre_variante = sub_raw
                    var.cantidad_stock = cant
                    var.precio_costo = Decimal(str(costo))
                    var.precio_minimo = Decimal(str(minimo))
                    var.precio_sugerido = Decimal(str(sugerido))
                    db.session.add(var)
                
                variantes_procesadas += 1
                
                # Kardex de variante
                if cant > 0:
                    ajuste = StockAdjustment()
                    ajuste.product_id = prod.id
                    ajuste.admin_id = current_user.id
                    ajuste.tipo_movimiento = f'Entrada Masiva (Subcat: {sub_raw})'
                    ajuste.stock_anterior = stock_ant
                    ajuste.stock_nuevo = var.cantidad_stock
                    db.session.add(ajuste)
            else:
                # PROCESAR COMO PRODUCTO BASE (Sin variante)
                stock_anterior = prod.cantidad_stock
                prod.cantidad_stock += cant
                            # Log de ajuste para actualización de producto base
                ajuste = StockAdjustment()
                ajuste.product_id = prod.id
                ajuste.admin_id = current_user.id
                ajuste.tipo_movimiento = 'Importación Masiva (Suma Base)'
                ajuste.stock_anterior = stock_anterior
                ajuste.stock_nuevo = prod.cantidad_stock
                db.session.add(ajuste)
                
        db.session.commit()
        flash(f'Carga masiva completada. Productos: {creados} creados / {actualizados} actualizados. Subcategorías procesadas: {variantes_procesadas}.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Ocurrió un error leyendo las filas de tu archivo: {str(e)}', 'danger')
        
    return redirect(url_for('inventory_bp.index'))

@inventory_bp.route('/search_attr', methods=['GET'])
@login_required
@inventory_access_required
def buscar_por_atributo():
    key = request.args.get('key')
    value = request.args.get('value')
    
    if not key or not value:
        flash('Debes proporcionar una llave y un valor para buscar.', 'warning')
        return redirect(url_for('inventory_bp.index'))
    
    tipo = 'bodega' if current_user.rol == 'bodega' else 'tienda'
    
    # Búsqueda dinámica en JSONB usando el operador de contención (@> en SQL)
    # SQLAlchemy: column.contains({key: value})
    productos = Product.query.filter(
        Product.tipo_inventario == tipo,
        Product.atributos.contains({key: value})
    ).all()
    
    # Re-utilizar la lógica de sumatorias del index para las tarjetas KPI
    total_unidades = 0
    valor_total_costo = 0.0
    valor_total_venta = 0.0
    for p in productos:
        if p.variantes:
            for v in p.variantes:
                total_unidades += v.cantidad_stock
                valor_total_costo += (v.cantidad_stock * float(v.precio_costo or p.precio_costo))
                valor_total_venta += (v.cantidad_stock * float(v.precio_sugerido or p.precio_sugerido))
        else:
            total_unidades += p.cantidad_stock
            valor_total_costo += (p.cantidad_stock * float(p.precio_costo))
            valor_total_venta += (p.cantidad_stock * float(p.precio_sugerido))
            
    return render_template('inventory/index.html', 
                           productos=productos, 
                           total_unidades=total_unidades, 
                           valor_total_costo=valor_total_costo, 
                           valor_total_venta=valor_total_venta,
                           busqueda_activa=f"Atributo: {key} = {value}")

# --- RUTAS DE GESTIÓN DE SERIALES ---

@inventory_bp.route('/producto/<int:id>/seriales', methods=['GET'])
@login_required
# Sin restricción de admin: el POS necesita consultar seriales para la selección de IMEI
def obtener_seriales(id):
    producto = Product.query.get_or_404(id)
    seriales = [{"id": s.id, "serial": s.serial, "estado": s.estado} for s in producto.series]
    return jsonify(seriales)

@inventory_bp.route('/producto/<int:id>/variantes', methods=['GET'])
@login_required
def obtener_variantes(id):
    producto = Product.query.get_or_404(id)
    variantes = [
        {
            "id": v.id,
            "nombre_variante": v.nombre_variante,
            "cantidad_stock": v.cantidad_stock,
            "precio_minimo": float(v.precio_minimo or producto.precio_minimo),
            "precio_final": float(v.precio_sugerido or producto.precio_sugerido)
        }
        for v in producto.variantes
    ]
    return jsonify(variantes)

@inventory_bp.route('/producto/<int:id>/seriales/agregar', methods=['POST'])
@login_required
@inventory_access_required
def agregar_serial(id):
    Product.query.get_or_404(id)
    serial_str = request.form.get('serial', '').strip()
    
    if not serial_str:
        return jsonify({"success": False, "error": "El serial no puede estar vacío."}), 400
        
    if ProductSeries.query.filter_by(serial=serial_str).first():
        return jsonify({"success": False, "error": "Este serial ya está registrado en el sistema."}), 400
        
    nuevo_serial = ProductSeries()
    nuevo_serial.product_id = id
    nuevo_serial.serial = serial_str
    nuevo_serial.estado = 'disponible'
    
    try:
        db.session.add(nuevo_serial)
        db.session.commit()
        return jsonify({"success": True, "id": nuevo_serial.id, "serial": nuevo_serial.serial})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@inventory_bp.route('/seriales/eliminar/<int:id>', methods=['POST'])
@login_required
@admin_or_bodega_required
def eliminar_serial(id):
    ser = ProductSeries.query.get_or_404(id)
    if ser.estado == 'vendido':
        return jsonify({"success": False, "error": "No se puede eliminar un serial que ya fue vendido."}), 400
        
    try:
        db.session.delete(ser)
        db.session.commit()
        return jsonify({"success": True})
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@inventory_bp.route('/retomas', methods=['GET'])
@login_required
@inventory_access_required
def retomas_index():
    retomas = ProductSeries.query.filter_by(estado='En Evaluación', origen='retoma').all()
    if not retomas:
        retomas = ProductSeries.query.filter_by(estado='En Evaluación').all()
    productos = Product.query.filter_by(es_serializado=True, tipo_inventario='tienda').all()
    categorias = Category.query.order_by(Category.nombre).all()
    return render_template('inventory/retomas.html', retomas=retomas, productos=productos, categorias=categorias)

@inventory_bp.route('/retomas/aprobadas', methods=['GET'])
@login_required
@inventory_access_required
def retomas_aprobadas():
    # Obtener retomas que ya pasaron la cuarentena (estado != 'En Evaluación')
    retomas = ProductSeries.query.filter(
        ProductSeries.origen == 'retoma',
        ProductSeries.estado != 'En Evaluación'
    ).all()
    return render_template('inventory/retomas_aprobadas.html', retomas=retomas)

@inventory_bp.route('/retomas/aprobar/<int:serie_id>', methods=['POST'])
@login_required
@inventory_access_required
def aprobar_retoma(serie_id):
    serie = ProductSeries.query.get_or_404(serie_id)
    if serie.estado != 'En Evaluación':
        flash('Esta unidad no está en evaluación.', 'warning')
        return redirect(url_for('inventory_bp.retomas_index'))
        
    accion = request.form.get('accion')
    
    try:
        if accion == 'existente':
            nuevo_prod_id = request.form.get('product_id')
            if not nuevo_prod_id:
                flash('Debe seleccionar un producto.', 'danger')
                return redirect(url_for('inventory_bp.retomas_index'))
                
            viejo_prod_id = serie.product_id
            serie.product_id = int(nuevo_prod_id)
            serie.estado = 'disponible'
            
            # Actualizar atributos comerciales del Producto General Destino
            prod_destino = Product.query.get(serie.product_id)
            if prod_destino:
                costo_compra = request.form.get('costo_compra')
                precio_sugerido = request.form.get('precio_sugerido')
                observacion = request.form.get('observacion')
                condicion = request.form.get('atributo_condicion')
                color = request.form.get('atributo_color')
                
                if costo_compra:
                    prod_destino.precio_costo = Decimal(str(costo_compra))
                    prod_destino.precio_minimo = Decimal(str(costo_compra))
                if precio_sugerido:
                    prod_destino.precio_sugerido = Decimal(str(precio_sugerido))
                if observacion:
                    prod_destino.observacion = observacion
                    
                # Update attributes JSONB
                attrs = prod_destino.atributos or {}
                if condicion:
                    attrs['Condición'] = condicion
                if color:
                    attrs['Color'] = color
                
                from sqlalchemy.orm.attributes import flag_modified
                prod_destino.atributos = attrs
                flag_modified(prod_destino, "atributos")

                # Categoría (solo actualiza el prod_destino si no tenía una)
                categoria_id = request.form.get('categoria_id')
                if categoria_id:
                    prod_destino.categoria_id = int(categoria_id)
            
            viejo_prod = Product.query.get(viejo_prod_id)
            if viejo_prod and viejo_prod.sku.startswith('RET-'):
                db.session.flush()
                if not viejo_prod.series:
                    db.session.delete(viejo_prod)
                
        elif accion == 'nuevo':
            serie.estado = 'disponible'
            prod = serie.producto
            prod.nombre = request.form.get('nuevo_nombre', prod.nombre)
            prod.precio_sugerido = float(request.form.get('nuevo_precio', prod.precio_sugerido))
            nueva_categoria_id = request.form.get('nueva_categoria_id')
            if nueva_categoria_id:
                prod.categoria_id = int(nueva_categoria_id)
            
        else:
            flash('Acción no válida.', 'danger')
            return redirect(url_for('inventory_bp.retomas_index'))
            
        db.session.commit()
        flash('Retoma aprobada y movida al inventario disponible.', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Error al aprobar retoma: {str(e)}', 'danger')
        
    return redirect(url_for('inventory_bp.retomas_index'))

@inventory_bp.route('/retomas/rechazar/<int:serie_id>', methods=['POST'])
@login_required
@admin_or_bodega_required
def rechazar_retoma(serie_id):
    serie = ProductSeries.query.get_or_404(serie_id)
    try:
        prod_id = serie.product_id
        db.session.delete(serie)
        
        db.session.flush()
        prod = Product.query.get(prod_id)
        if prod and prod.sku.startswith('RET-') and not prod.series:
            db.session.delete(prod)
            
        db.session.commit()
        flash('Retoma eliminada/rechazada.', 'success')
    except Exception:
        db.session.rollback()
        flash('Error al eliminar retoma.', 'danger')
    return redirect(url_for('inventory_bp.retomas_index'))

@inventory_bp.route('/retomas/aprobadas/eliminar/<int:serie_id>', methods=['POST'])
@login_required
@admin_or_bodega_required
def eliminar_retoma_aprobada(serie_id):
    serie = ProductSeries.query.get_or_404(serie_id)

    if serie.estado == 'vendido':
        flash('No se puede eliminar un IMEI que ya fue vendido.', 'danger')
        return redirect(url_for('inventory_bp.retomas_aprobadas'))

    try:
        prod_id = serie.product_id
        db.session.delete(serie)
        db.session.flush()

        prod = Product.query.get(prod_id)
        if prod and prod.sku.startswith('RET-') and not prod.series:
            # Producto provisional sin más seriales → se borra completo
            db.session.delete(prod)
        # Si es producto oficial, solo se eliminó el serial; el producto queda

        db.session.commit()
        flash('Retoma eliminada del inventario correctamente.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Error al eliminar: {str(e)}', 'danger')

    return redirect(url_for('inventory_bp.retomas_aprobadas'))

@inventory_bp.route('/catalogo_pdf', methods=['POST'])
@login_required
def catalogo_pdf():
    import json
    import html
    from io import BytesIO

    try:
        from reportlab.lib.pagesizes import letter
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, HRFlowable
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib import colors
    except ImportError:
        flash("El módulo ReportLab no está disponible en el servidor.", "danger")
        return redirect(url_for('inventory_bp.index'))

    raw_ids = request.form.get('product_ids', '[]')
    try:
        product_ids = json.loads(raw_ids)
    except Exception:
        product_ids = []

    if not product_ids:
        flash("No se seleccionaron productos para el catálogo.", "warning")
        return redirect(url_for('inventory_bp.index'))

    productos = Product.query.filter(Product.id.in_(product_ids)).all()
    if not productos:
        flash("Los productos seleccionados ya no están disponibles.", "warning")
        return redirect(url_for('inventory_bp.index'))

    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=letter, rightMargin=36, leftMargin=36, topMargin=36, bottomMargin=36)
    story = []

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1A1A1A'),
        alignment=1,
        fontName='Helvetica-Bold'
    )
    subtitle_style = ParagraphStyle(
        'DocSubTitle',
        parent=styles['Normal'],
        fontSize=10,
        leading=13,
        textColor=colors.HexColor('#666666'),
        alignment=1,
        fontName='Helvetica'
    )
    prod_desc = ParagraphStyle(
        'ProdDesc',
        parent=styles['Normal'],
        fontSize=9,
        leading=12,
        textColor=colors.HexColor('#222222'),
        fontName='Helvetica'
    )
    price_style = ParagraphStyle(
        'ProdPrice',
        parent=styles['Normal'],
        fontSize=12,
        leading=15,
        textColor=colors.HexColor('#C59F60'),
        fontName='Helvetica-Bold'
    )
    footer_style = ParagraphStyle(
        'DocFooter',
        parent=styles['Normal'],
        fontSize=9,
        leading=11,
        textColor=colors.HexColor('#444444'),
        alignment=1,
        fontName='Helvetica-Bold'
    )

    story.append(Paragraph("<b>DTAVO — CATÁLOGO DE PRODUCTOS</b>", title_style))
    story.append(Spacer(1, 4))
    fecha_str = obtener_hora_bogota().strftime('%d/%m/%Y %H:%M')
    story.append(Paragraph(f"Generado el {fecha_str} | Aliado tecnológico ZENIC SAS", subtitle_style))
    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#C59F60'), spaceAfter=15))

    for p in productos:
        img_element = None
        if p.imagen:
            img_path = os.path.join(current_app.root_path, 'static', 'uploads', p.imagen)
            if os.path.exists(img_path):
                try:
                    from PIL import Image as PILImage
                    with PILImage.open(img_path) as pil_img:
                        w, h = pil_img.size
                        aspect = h / float(w or 1)
                        target_w = 120
                        target_h = int(target_w * aspect)
                        if target_h > 120:
                            target_h = 120
                            target_w = int(target_h / (aspect or 1))
                        img_element = Image(img_path, width=target_w, height=target_h)
                except Exception:
                    try:
                        img_element = Image(img_path, width=110, height=110)
                    except Exception:
                        img_element = None

        if not img_element:
            img_element = Paragraph("<br/><br/><font color='#9CA3AF' size=9><b>[ Sin imagen disponible ]</b></font>", subtitle_style)

        # Escapar caracteres HTML especiales para prevenir fallos de XML en ReportLab
        safe_nombre = html.escape(p.nombre or '')
        safe_cat = html.escape(p.categoria.nombre if p.categoria else 'General')
        safe_obs = html.escape(p.observacion or '')

        user_attrs = []
        if p.atributos:
            for k, v in p.atributos.items():
                if k != 'stock_minimo_alerta' and str(v).strip():
                    safe_k = html.escape(str(k))
                    safe_v = html.escape(str(v))
                    user_attrs.append(f"<b>{safe_k}:</b> {safe_v}")
        
        attr_text = ""
        if user_attrs:
            attr_text = "<br/><font size=9 color='#374151'>" + " &nbsp;•&nbsp; ".join(user_attrs) + "</font>"
        
        cat_info = f"<font size=9 color='#6B7280'>Categoría: {safe_cat}</font>"
        obs_info = f"<br/><font size=9 color='#4B5563'><i>{safe_obs}</i></font>" if safe_obs.strip() else ""

        detail_html = f"<b><font size=13 color='#111827'>{safe_nombre}</font></b><br/>{cat_info}{attr_text}{obs_info}"
        detail_p = Paragraph(detail_html, prod_desc)

        precio_cop = "{:,.0f}".format(float(p.precio_sugerido or 0))
        price_p = Paragraph(f"<b><font size=13 color='#C59F60'>PRECIO: ${precio_cop}</font></b>", price_style)

        right_flowables = [detail_p, Spacer(1, 10), price_p]

        table_data = [[img_element, right_flowables]]
        t = Table(table_data, colWidths=[130, 410])
        t.setStyle(TableStyle([
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FFFFFF')),
            ('BOX', (0, 0), (-1, -1), 0.75, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 10),
        ]))
        story.append(t)
        story.append(Spacer(1, 12))

    story.append(Spacer(1, 10))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor('#C59F60'), spaceAfter=8))
    story.append(Paragraph("<b>Aliado tecnológico ZENIC SAS</b>", footer_style))

    try:
        doc.build(story)
        buffer.seek(0)
        return send_file(buffer, as_attachment=True, download_name=f"catalogo_dtavo_{obtener_hora_bogota().strftime('%Y%m%d_%H%M')}.pdf", mimetype='application/pdf')
    except Exception as e:
        current_app.logger.error(f"Error generando PDF del catálogo: {e}")
        flash(f"Error al generar el PDF del catálogo: {str(e)}", "danger")
        return redirect(url_for('inventory_bp.index'))
