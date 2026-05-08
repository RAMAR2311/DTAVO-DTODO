from app import app
from models import Product, ProductVariant

with app.app_context():
    p = Product.query.filter_by(sku='ROP-002').first()
    if p:
        print(f"Producto: {p.nombre} (ID: {p.id})")
        print(f"Tiene Variantes (rel): {len(p.variantes)}")
        for v in p.variantes:
            print(f" - Variante: {v.nombre_variante}, Stock: {v.cantidad_stock}")
    else:
        print("Producto ROP-002 no encontrado.")
