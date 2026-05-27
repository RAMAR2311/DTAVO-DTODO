# -*- coding: utf-8 -*-
from app import create_app
from models import db, ArqueoCaja

def recreate_table():
    app = create_app()
    with app.app_context():
        try:
            # Eliminar la tabla antigua
            ArqueoCaja.__table__.drop(db.engine, checkfirst=True)
            print("[INFO] Tabla arqueo_caja eliminada con éxito (si existía).")
            
            # Crear la tabla nueva con el nuevo esquema
            ArqueoCaja.__table__.create(db.engine, checkfirst=True)
            print("[SUCCESS] Tabla arqueo_caja creada exitosamente con el esquema actualizado.")
        except Exception as e:
            print(f"[ERROR] Error recreando la tabla: {e}")

if __name__ == '__main__':
    recreate_table()
