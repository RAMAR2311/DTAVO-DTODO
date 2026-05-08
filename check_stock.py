from app import app
from models import Product

with app.app_context():
    p = Product.query.filter_by(sku='BUZ-OVR-001').first()
    if p:
        print(f"Producto: {p.nombre}")
        print(f"Stock Base: {p.cantidad_stock}")
        print(f"Total Stock (property): {p.total_stock}")
        for v in p.variantes:
            print(f" - Variante: {v.nombre_variante}, Stock: {v.cantidad_stock}")
