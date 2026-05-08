from app import app
from models import db

with app.app_context():
    try:
        db.session.execute(db.text("ALTER TABLE arqueo_caja ADD COLUMN total_ventas NUMERIC(14, 2) DEFAULT 0.0;"))
        db.session.execute(db.text("ALTER TABLE arqueo_caja ADD COLUMN desglose_categorias JSONB DEFAULT '{}';"))
        db.session.commit()
        print("Columnas añadidas a arqueo_caja.")
    except Exception as e:
        db.session.rollback()
        print(f"Error o ya existían: {e}")
