from app import app
from models import Category, Product

with app.app_context():
    cats = Category.query.all()
    for c in cats:
        print(f"Categoría: {c.nombre} (ID: {c.id})")
        prods = Product.query.filter_by(categoria_id=c.id).all()
        for p in prods:
            print(f"  - Producto: {p.nombre} (SKU: {p.sku}), Variantes: {len(p.variantes)}")
