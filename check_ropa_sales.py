from app import app
from models import db, Product, Category, ProductVariant, SaleDetail

with app.app_context():
    cat = Category.query.filter(Category.nombre.ilike('ropa')).first()
    if not cat:
        print("Categoría Ropa no encontrada.")
    else:
        print(f"Categoría: {cat.nombre} (ID: {cat.id})")
        prods = Product.query.filter_by(categoria_id=cat.id).all()
        print(f"Productos encontrados: {len(prods)}")
        
        has_sales = False
        for p in prods:
            if SaleDetail.query.filter_by(product_id=p.id).first():
                print(f" - El producto {p.nombre} tiene ventas asociadas.")
                has_sales = True
        
        if not has_sales:
            print("No hay ventas asociadas a estos productos. Se pueden borrar.")
        else:
            print("CUIDADO: Hay ventas asociadas. El borrado fallará por integridad referencial.")
