from app import app
from models import db, Product, ProductVariant, Category, StockAdjustment, SaleDetail, Sale

with app.app_context():
    # 1. Identificar categoría
    cat = Category.query.filter(Category.nombre.ilike('ropa')).first()
    if not cat:
        print("Categoría Ropa no encontrada.")
        exit()
    
    print(f"Limpiando categoría: {cat.nombre} (ID: {cat.id})")
    
    # 2. Obtener productos
    prods = Product.query.filter_by(categoria_id=cat.id).all()
    prod_ids = [p.id for p in prods]
    
    # 3. Borrar registros dependientes
    # Borrar ajustes de stock
    StockAdjustment.query.filter(StockAdjustment.product_id.in_(prod_ids)).delete(synchronize_session=False)
    
    # Borrar detalles de venta (y opcionalmente la venta si queda vacía)
    details = SaleDetail.query.filter(SaleDetail.product_id.in_(prod_ids)).all()
    sale_ids = set(d.sale_id for d in details)
    for d in details:
        db.session.delete(d)
    
    # Borrar variantes
    ProductVariant.query.filter(ProductVariant.product_id.in_(prod_ids)).delete(synchronize_session=False)
    
    # Borrar productos
    for p in prods:
        db.session.delete(p)
    
    db.session.commit()
    print(f"Se eliminaron {len(prods)} productos de ropa y sus registros asociados.")

    # 4. Agregar Nuevos Ejemplos
    ejemplos = [
        {
            "sku": "CAM-OVR-001",
            "nombre": "Camiseta Oversize Algodón",
            "precio_costo": 25000,
            "precio_sugerido": 55000,
            "variantes": [
                {"nombre": "Negra / S", "stock": 10},
                {"nombre": "Negra / M", "stock": 15},
                {"nombre": "Negra / L", "stock": 10},
                {"nombre": "Blanca / M", "stock": 12},
            ]
        },
        {
            "sku": "JEAN-SK-002",
            "nombre": "Jean Skinny Fit Stretch",
            "precio_costo": 45000,
            "precio_sugerido": 95000,
            "variantes": [
                {"nombre": "Azul / 30", "stock": 5},
                {"nombre": "Azul / 32", "stock": 8},
                {"nombre": "Azul / 34", "stock": 5},
                {"nombre": "Negro / 32", "stock": 6},
            ]
        },
        {
            "sku": "CHQ-CUE-003",
            "nombre": "Chaqueta Eco-Cuero Black",
            "precio_costo": 85000,
            "precio_sugerido": 185000,
            "variantes": [
                {"nombre": "Talla M", "stock": 4},
                {"nombre": "Talla L", "stock": 3},
            ]
        },
        {
            "sku": "ACC-CAL-004",
            "nombre": "Pack 3 Pares Calcetines",
            "precio_costo": 8000,
            "precio_sugerido": 18000,
            "cantidad_stock": 50, # Stock plano
            "variantes": []
        }
    ]

    for ej in ejemplos:
        p = Product()
        p.sku = ej["sku"]
        p.nombre = ej["nombre"]
        p.categoria_id = cat.id
        p.tipo_inventario = 'tienda'
        p.precio_costo = ej["precio_costo"]
        p.precio_minimo = ej["precio_sugerido"] * 0.8
        p.precio_sugerido = ej["precio_sugerido"]
        p.cantidad_stock = ej.get("cantidad_stock", 0)
        
        db.session.add(p)
        db.session.flush()
        
        for v_data in ej["variantes"]:
            v = ProductVariant()
            v.product_id = p.id
            v.nombre_variante = v_data["nombre"]
            v.cantidad_stock = v_data["stock"]
            v.precio_costo = p.precio_costo
            v.precio_minimo = p.precio_minimo
            v.precio_sugerido = p.precio_sugerido
            db.session.add(v)
            
        # Kardex
        ajuste = StockAdjustment()
        ajuste.product_id = p.id
        ajuste.admin_id = 1 # Asumiendo admin ID 1
        ajuste.tipo_movimiento = 'Re-sembrado de Ejemplos'
        ajuste.stock_anterior = 0
        ajuste.stock_nuevo = p.total_stock
        db.session.add(ajuste)

    db.session.commit()
    print("Nuevos ejemplos de ropa agregados exitosamente.")
