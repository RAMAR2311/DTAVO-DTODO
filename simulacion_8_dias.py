import random
from datetime import datetime, timedelta
from decimal import Decimal
from app import app
from models import db, Product, ProductVariant, ProductSeries, Category, Sale, SaleDetail, SalePayment, Customer, ArqueoCaja

def seed_simulation():
    with app.app_context():
        print("Iniciando limpieza total...")
        # Limpieza (CASCADE se encarga de los hijos)
        db.session.query(ArqueoCaja).delete()
        db.session.query(SalePayment).delete()
        db.session.query(SaleDetail).delete()
        db.session.query(ProductSeries).delete()
        db.session.query(ProductVariant).delete()
        db.session.query(Sale).delete()
        db.session.query(Product).delete()
        db.session.query(Customer).delete()
        # Nota: Categorías se mantienen pero verificamos existencia
        db.session.commit()
        print("Base de datos limpia.")

        # 1. Asegurar Categorías
        cat_names = ['Celulares', 'Tecnología', 'Ropa', 'Accesorios']
        cats = {}
        for name in cat_names:
            c = Category.query.filter(Category.nombre.ilike(name)).first()
            if not c:
                c = Category(nombre=name)
                db.session.add(c)
                db.session.flush()
            cats[name] = c.id
        db.session.commit()

        # 2. Clientes
        clientes = []
        for i in range(5):
            cli = Customer(
                nombre=f"Cliente Simulado {i+1}",
                cedula=f"1090{i}88{random.randint(100,999)}",
                telefono=f"310{random.randint(1000000,9999999)}"
            )
            db.session.add(cli)
            clientes.append(cli)
        db.session.flush()

        # 3. Productos
        productos_pool = []
        
        # CELULARES (Serializados)
        cel_models = [
            ("iPhone 15 Pro", 4500000),
            ("S24 Ultra", 4200000),
            ("Xiaomi 14", 2800000),
            ("Pixel 8", 3100000),
            ("Motorola Edge", 1800000)
        ]
        for name, price in cel_models:
            p = Product(
                nombre=name, sku=f"CEL-{name[:3].upper()}-{random.randint(100,999)}",
                categoria_id=cats['Celulares'], precio_costo=price*0.8,
                precio_minimo=price*0.9, precio_sugerido=price,
                es_serializado=True, cantidad_stock=5
            )
            db.session.add(p)
            db.session.flush()
            for i in range(5):
                s = ProductSeries(product_id=p.id, serial=f"IMEI-{p.sku}-{i+1}", estado='disponible')
                db.session.add(s)
            productos_pool.append(p)

        # TECNOLOGÍA
        tec_models = [
            ("AirPods Pro", 950000),
            ("MacBook Air M2", 5500000),
            ("Apple Watch S9", 1850000),
            ("Tablet Samsung S9", 2200000),
            ("Cargador 20W", 85000)
        ]
        for name, price in tec_models:
            p = Product(
                nombre=name, sku=f"TEC-{name[:3].upper()}-{random.randint(100,999)}",
                categoria_id=cats['Tecnología'], precio_costo=price*0.7,
                precio_minimo=price*0.9, precio_sugerido=price,
                cantidad_stock=20
            )
            db.session.add(p)
            productos_pool.append(p)

        # ROPA (Con Variantes)
        ropa_models = [
            ("Hoodie Gold TAVO", 120000),
            ("Camiseta Premium", 45000),
            ("Pantalón Jogger", 85000),
            ("Gorra TAVO Logo", 35000),
            ("Chaqueta Bomber", 185000)
        ]
        for name, price in ropa_models:
            p = Product(
                nombre=name, sku=f"ROP-{name[:3].upper()}-{random.randint(100,999)}",
                categoria_id=cats['Ropa'], precio_costo=price*0.5,
                precio_minimo=price*0.8, precio_sugerido=price,
                cantidad_stock=40 # Suma de variantes
            )
            db.session.add(p)
            db.session.flush()
            for sz in ["S", "M", "L", "XL"]:
                v = ProductVariant(
                    product_id=p.id, nombre_variante=sz, cantidad_stock=10,
                    precio_costo=p.precio_costo, precio_minimo=p.precio_minimo, precio_sugerido=p.precio_sugerido
                )
                db.session.add(v)
            productos_pool.append(p)

        # ACCESORIOS
        acc_models = [
            ("Gafas Aviador", 65000),
            ("Billetera Cuero", 45000),
            ("Reloj Análogo", 125000),
            ("Correa Titanio", 75000),
            ("Llavero Luxury", 25000)
        ]
        for name, price in acc_models:
            p = Product(
                nombre=name, sku=f"ACC-{name[:3].upper()}-{random.randint(100,999)}",
                categoria_id=cats['Accesorios'], precio_costo=price*0.4,
                precio_minimo=price*0.8, precio_sugerido=price,
                cantidad_stock=30
            )
            db.session.add(p)
            productos_pool.append(p)

        db.session.commit()
        print("Productos e Inventario creados.")

        # 4. Simulación de Ventas y Arqueos
        start_date = datetime(2026, 5, 1, 9, 0)
        metodos = ['efectivo', 'tarjeta', 'transferencia']
        
        for day in range(8): # Del 1 al 8 de Mayo
            current_day_date = start_date + timedelta(days=day)
            print(f"Simulando Día {current_day_date.date()}...")
            
            daily_total = Decimal('0.00')
            nicho_stats = {cat: Decimal('0.00') for cat in cat_names}
            
            num_sales = random.randint(2, 4)
            for s_idx in range(num_sales):
                # Crear Venta
                sale_time = current_day_date + timedelta(hours=random.randint(1, 8), minutes=random.randint(0,59))
                
                # Elegir Nicho para esta venta
                nicho_v_name = random.choice(cat_names)
                nicho_v_id = cats[nicho_v_name]
                
                cli = random.choice(clientes)
                
                venta = Sale(
                    vendedor_id=1, cliente_id=cli.id, cliente_nombre=cli.nombre,
                    fecha_venta=sale_time, metodo_pago=random.choice(metodos),
                    categoria_id=nicho_v_id, monto_total=0
                )
                db.session.add(venta)
                db.session.flush()
                
                # Agregar 1-2 productos de ESE nicho
                nicho_prods = [p for p in productos_pool if p.categoria_id == nicho_v_id]
                sale_monto = Decimal('0.00')
                
                items_in_sale = random.sample(nicho_prods, k=random.randint(1, min(2, len(nicho_prods))))
                for p in items_in_sale:
                    qty = 1
                    price = p.precio_sugerido
                    
                    detalle = SaleDetail(
                        sale_id=venta.id, product_id=p.id, cantidad_vendida=qty,
                        precio_venta_final=price
                    )
                    
                    # Manejo especial
                    if p.es_serializado:
                        ser = ProductSeries.query.filter_by(product_id=p.id, estado='disponible').first()
                        if ser:
                            ser.estado = 'vendido'
                            detalle.serial_vendido = ser.serial
                            db.session.flush()
                            ser.sale_detail_id = detalle.id
                            p.cantidad_stock -= 1
                    elif p.variantes:
                        var = random.choice(p.variantes)
                        var.cantidad_stock -= qty
                        detalle.variant_id = var.id
                        p.cantidad_stock -= qty
                    else:
                        p.cantidad_stock -= qty
                    
                    db.session.add(detalle)
                    sale_monto += (price * qty)
                
                venta.monto_total = sale_monto
                
                # Pago
                pago = SalePayment(sale_id=venta.id, metodo_pago=venta.metodo_pago, monto=sale_monto)
                db.session.add(pago)
                
                daily_total += sale_monto
                nicho_stats[nicho_v_name] += sale_monto
            
            db.session.commit()
            
            # Crear Arqueo si es del 1 al 7
            if day < 7:
                arqueo = ArqueoCaja(
                    vendedor_id=1, 
                    fecha_arqueo=current_day_date.date(),
                    total_ventas=daily_total,
                    base_inicial=Decimal('100000.00'),
                    gastos_del_dia=Decimal('0.00'),
                    total_efectivo_sistema=daily_total * Decimal('0.6'), # Simulación de mix
                    total_transferencia_sistema=daily_total * Decimal('0.4'),
                    observaciones_gastos=f"Cierre automático día {day+1}",
                    desglose_categorias={ k: float(v) for k, v in nicho_stats.items() }
                )
                db.session.add(arqueo)
                db.session.commit()

        print("Simulación completada con éxito.")

if __name__ == "__main__":
    seed_simulation()
