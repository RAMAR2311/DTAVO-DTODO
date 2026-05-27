# -*- coding: utf-8 -*-
from app import create_app
from models import db, ArqueoCaja, User
from datetime import datetime, timedelta
import pytz

def seed_historical_arqueos():
    app = create_app()
    with app.app_context():
        # Obtener un usuario para asociar al cierre de caja
        user = User.query.filter_by(rol='admin').first() or User.query.first()
        if not user:
            print("[ERROR] No se encontró ningún usuario en la base de datos para asociar el arqueo.")
            return

        timezone = pytz.timezone('America/Bogota')
        base_time = datetime.now(timezone).replace(tzinfo=None)

        print(f"[SEED] Insertando cierres de caja históricos con el nuevo esquema...")

        # Cierre 1: Hace 1 día (Caja Cuadrada)
        fecha_1 = base_time - timedelta(days=1)
        # Limpiar cierres previos si los hubiera (para evitar errores de restricción de clave única)
        db.session.query(ArqueoCaja).delete()
        cierre_1 = ArqueoCaja(
            vendedor_id=user.id,
            fecha_arqueo=fecha_1.date(),
            base_inicial=200000.0,
            total_ventas=1850000.0,
            gastos_del_dia=50000.0,
            observaciones_gastos="Se pagó almuerzo del personal ($35,000) y papelería ($15,000).",
            total_efectivo_sistema=1200000.0,
            total_transferencia_sistema=650000.0,
            efectivo_fisico=1350000.0,   # Esperado: 200k + 1.2M - 50k = 1.35M
            diferencia=0.0,
            observacion_diferencia="Caja cuadrada sin novedades.",
            desglose_categorias={"Celulares": 1500000.0, "Ropa": 350000.0},
            desglose_pagos={"efectivo": 1200000.0, "transferencia": 650000.0},
            fecha_creacion=fecha_1
        )
        db.session.add(cierre_1)

        # Cierre 2: Hace 2 días (Caja Faltante de $20,000)
        fecha_2 = base_time - timedelta(days=2)
        cierre_2 = ArqueoCaja(
            vendedor_id=user.id,
            fecha_arqueo=fecha_2.date(),
            base_inicial=150000.0,
            total_ventas=3200000.0,
            gastos_del_dia=120000.0,
            observaciones_gastos="Servicio de limpieza general profunda ($70,000) y transporte de mercancías ($50,000).",
            total_efectivo_sistema=2000000.0,
            total_transferencia_sistema=1200000.0,
            efectivo_fisico=2010000.0,   # Esperado: 150k + 2M - 120k = 2.03M
            diferencia=-20000.0,        # Faltante de 20k
            observacion_diferencia="Faltante de $20,000 debido a cambio mal entregado en una venta en efectivo congestionada.",
            desglose_categorias={"Celulares": 2800000.0, "Accesorios": 400000.0},
            desglose_pagos={"efectivo": 2000000.0, "transferencia": 800000.0, "retoma": 400000.0},
            fecha_creacion=fecha_2
        )
        db.session.add(cierre_2)

        # Cierre 3: Hace 3 días (Caja Sobrante de $10,000)
        fecha_3 = base_time - timedelta(days=3)
        cierre_3 = ArqueoCaja(
            vendedor_id=user.id,
            fecha_arqueo=fecha_3.date(),
            base_inicial=200000.0,
            total_ventas=950000.0,
            gastos_del_dia=0.0,
            observaciones_gastos="Cierre dominical consolidado sin novedades ni gastos registrados.",
            total_efectivo_sistema=450000.0,
            total_transferencia_sistema=500000.0,
            efectivo_fisico=660000.0,    # Esperado: 200k + 450k - 0 = 650k
            diferencia=10000.0,         # Sobrante de 10k
            observacion_diferencia="Sobrante de $10,000. Probable propina o cliente no reclamó vueltas de monto menor.",
            desglose_categorias={"Ropa": 950000.0},
            desglose_pagos={"efectivo": 450000.0, "transferencia": 500000.0},
            fecha_creacion=fecha_3
        )
        db.session.add(cierre_3)

        # Cierre 4: Hace 5 días (Caja Cuadrada)
        fecha_5 = base_time - timedelta(days=5)
        cierre_4 = ArqueoCaja(
            vendedor_id=user.id,
            fecha_arqueo=fecha_5.date(),
            base_inicial=100000.0,
            total_ventas=4500000.0,
            gastos_del_dia=250000.0,
            observaciones_gastos="Pago de factura de internet y servicios ($180,000) y suministros de cafetería ($70,000).",
            total_efectivo_sistema=3000000.0,
            total_transferencia_sistema=1500000.0,
            efectivo_fisico=2850000.0,   # Esperado: 100k + 3M - 250k = 2.85M
            diferencia=0.0,
            observacion_diferencia="Caja cuadrada.",
            desglose_categorias={"Celulares": 4000000.0, "Ropa": 500000.0},
            desglose_pagos={"efectivo": 3000000.0, "transferencia": 1500000.0},
            fecha_creacion=fecha_5
        )
        db.session.add(cierre_4)

        db.session.commit()
        print("[SUCCESS] Se han creado y registrado con éxito los 4 cierres históricos actualizados en la base de datos.")

if __name__ == '__main__':
    seed_historical_arqueos()
