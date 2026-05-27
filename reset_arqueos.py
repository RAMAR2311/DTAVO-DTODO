# -*- coding: utf-8 -*-
from app import create_app
from models import db, ArqueoCaja

def reset_arqueos():
    app = create_app()
    with app.app_context():
        num_deleted = db.session.query(ArqueoCaja).delete()
        db.session.commit()
        print(f"[RESET] Caja reestablecida con éxito. Se eliminaron {num_deleted} cierres de caja anteriores.")

if __name__ == '__main__':
    reset_arqueos()
