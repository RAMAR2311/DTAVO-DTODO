from app import app
from models import db, Product, ProductVariant, Category, StockAdjustment, SaleDetail

with app.app_context():
    # 1. Identificar categoría Ropa
    cat = Category.query.filter(Category.nombre.ilike('ropa')).first()
    if not cat:
        print("Categoría Ropa no encontrada.")
        exit()
    
    # 2. Borrar productos de ropa actuales
    prods = Product.query.filter_by(categoria_id=cat.id).all()
    for p in prods:
        # Borrar registros vinculados
        StockAdjustment.query.filter_by(product_id=p.id).delete()
        SaleDetail.query.filter_by(product_id=p.id).delete()
        ProductVariant.query.filter_by(product_id=p.id).delete()
        db.session.delete(p)
    
    db.session.commit()
    print("Módulo de ropa limpiado.")

    # 3. Agregar Productos de Referencia
    referencias = [
        {
            "sku": "GOR-TAV-001",
            "nombre": "Gorra Trucker TAVO Edition",
            "precio_costo": 15000,
            "precio_sugerido": 35000,
            "variantes": [
                {"nombre": "Talla Única", "stock": 20}
            ]
        },
        {
            "sku": "PAN-JEA-002",
            "nombre": "Pantalón Jean Azul Clásico",
            "precio_costo": 45000,
            "precio_sugerido": 98000,
            "variantes": [
                {"nombre": "30", "stock": 5},
                {"nombre": "32", "stock": 10},
                {"nombre": "34", "stock": 8},
                {"nombre": "36", "stock": 4}
            ]
        },
        {
            "sku": "CAM-BAS-003",
            "nombre": "Camiseta Básica Algodón Pima",
            "precio_costo": 22000,
            "precio_sugerido": 45000,
            "variantes": [
                {"nombre": "S", "stock": 12},
                {"nombre": "M", "stock": 20},
                {"nombre": "L", "stock": 15},
                {"nombre": "XL", "stock": 10}
            ]
        },
        {
            "sku": "ZAP-CUE-004",
            "nombre": "Zapatos de Cuero Formal",
            "precio_costo": 95000,
            "precio_sugerido": 210000,
            "variantes": [
                {"nombre": "38", "stock": 3},
                {"nombre": "40", "stock": 5},
                {"nombre": "42", "stock": 4}
            ]
        }
    ]

    for ref in referencias:
        p = Product()
        p.sku = ref["sku"]
        p.nombre = ref["nombre"]
        p.categoria_id = cat.id
        p.tipo_inventario = 'tienda'
        p.precio_costo = ref["precio_costo"]
        p.precio_minimo = ref["precio_sugerido"] * 0.85
        p.precio_sugerido = ref["precio_sugerido"]
        p.cantidad_stock = sum(v["stock"] for v in ref["variantes"])
        
        db.session.add(p)
        db.session.flush()
        
        for v_data in ref["variantes"]:
            v = ProductVariant()
            v.product_id = p.id
            v.nombre_variante = v_data["nombre"]
            v.cantidad_stock = v_data["stock"]
            v.precio_costo = p.precio_costo
            v.precio_minimo = p.precio_minimo
            v.precio_sugerido = p.precio_sugerido
            db.session.add(v)

    db.session.commit()
    print("Productos de referencia agregados exitosamente.")
