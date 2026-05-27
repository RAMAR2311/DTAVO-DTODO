# -*- coding: utf-8 -*-
"""
Script de ejemplo: Registra una venta mixta con un pago en efectivo
y un pago en retoma (celular recibido como parte de pago),
demostrando la integración completa en el historial y cierre de caja.
"""
import sys
import io
import os
import uuid
from decimal import Decimal

# Forzar UTF-8 en consola
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from app import create_app
from models import db, User, Product, ProductSeries, Sale, SaleDetail, SalePayment, Category, obtener_hora_bogota

def inyectar_ejemplo():
    app = create_app()
    with app.app_context():
        print("=" * 60)
        print("🚀 INYECTANDO VENTA DE EJEMPLO CON MÉTODO DE PAGO: RETOMA")
        print("=" * 60)

        # 1. Obtener/Crear Categoría Celulares
        cat = Category.query.filter(Category.nombre.ilike('%celular%')).first()
        if not cat:
            cat = Category.query.get(6)
        if not cat:
            cat = Category.query.get(1)
        if not cat:
            cat = Category(nombre='Celulares', descripcion='Celulares y smartphones')
            db.session.add(cat)
            db.session.commit()
        print(f"[OK] Categoría de venta: '{cat.nombre}' (ID: {cat.id})")

        # 2. Obtener/Crear Producto Vendido
        producto = Product.query.filter_by(sku='IP15PM-TEST').first()
        if not producto:
            producto = Product(
                nombre='iPhone 15 Pro Max 256GB (TEST)',
                sku='IP15PM-TEST',
                tipo_inventario='tienda',
                es_serializado=True,
                categoria_id=cat.id,
                precio_costo=Decimal('3500000'),
                precio_minimo=Decimal('4200000'),
                precio_sugerido=Decimal('4500000')
            )
            db.session.add(producto)
            db.session.commit()
        print(f"[OK] Producto vendido: '{producto.nombre}' (ID: {producto.id})")

        # 3. Serial disponible para la venta
        serial_vendido = '357111222333444'
        serie_vendida = ProductSeries.query.filter_by(serial=serial_vendido).first()
        if not serie_vendida:
            serie_vendida = ProductSeries(
                product_id=producto.id,
                serial=serial_vendido,
                estado='disponible',
                origen='sistema'
            )
            db.session.add(serie_vendida)
            db.session.commit()
        else:
            serie_vendida.estado = 'disponible'
            serie_vendida.sale_detail_id = None
            db.session.commit()
        print(f"[OK] Serial a vender listo: {serial_vendido}")

        # 4. Obtener Vendedor
        vendedor = User.query.filter_by(rol='admin').first() or User.query.first()
        print(f"[OK] Vendedor asignado: '{vendedor.nombre}'")

        # 5. Crear Venta
        # Precio de venta final: $4,500,000
        # Pago: $3,000,000 en efectivo + $1,500,000 en retoma (celular recibido)
        monto_total = Decimal('4500000')
        monto_efectivo = Decimal('3000000')
        monto_retoma = Decimal('1500000')

        nueva_venta = Sale(
            vendedor_id=vendedor.id,
            cliente_nombre='Pedro Gomez (RETOMA DEMO)',
            monto_total=monto_total,
            metodo_pago='mixto', # Pago mixto (Efectivo + Retoma)
            categoria_id=cat.id,
            fecha_venta=obtener_hora_bogota()
        )
        db.session.add(nueva_venta)
        db.session.flush()

        # 6. Registrar Detalle de Venta
        detalle = SaleDetail(
            sale_id=nueva_venta.id,
            product_id=producto.id,
            cantidad_vendida=1,
            precio_venta_final=monto_total,
            serial_vendido=serial_vendido,
            bateria='98%',
            estado_producto='Seminuevo',
            tiempo_garantia='6 meses'
        )
        db.session.add(detalle)
        db.session.flush()

        # Marcar serial vendido
        serie_vendida.estado = 'vendido'
        serie_vendida.sale_detail_id = detalle.id
        db.session.add(serie_vendida)

        # 7. Registrar los 2 pagos (Efectivo + Retoma)
        pago_efe = SalePayment(
            sale_id=nueva_venta.id,
            metodo_pago='efectivo',
            monto=monto_efectivo
        )
        db.session.add(pago_efe)

        pago_ret = SalePayment(
            sale_id=nueva_venta.id,
            metodo_pago='retoma',
            monto=monto_retoma
        )
        db.session.add(pago_ret)

        # 8. Ingresar celular de retoma al inventario (En Evaluación / Cuarentena)
        modelo_retoma = 'iPhone 12 Pro 128GB (RETOMA TEST)'
        imei_retoma = '359999999999999'

        prod_retoma = Product.query.filter_by(nombre=modelo_retoma, tipo_inventario='tienda').first()
        if not prod_retoma:
            prod_retoma = Product(
                nombre=modelo_retoma,
                sku=f"RET-{uuid.uuid4().hex[:6].upper()}",
                tipo_inventario='tienda',
                es_serializado=True,
                precio_costo=monto_retoma,
                precio_minimo=monto_retoma,
                precio_sugerido=monto_retoma * Decimal('1.2'),
                categoria_id=cat.id,
                observacion='Recibido como retoma en venta #' + str(nueva_venta.id)
            )
            db.session.add(prod_retoma)
            db.session.flush()

        serie_retoma = ProductSeries.query.filter_by(serial=imei_retoma).first()
        if not serie_retoma:
            serie_retoma = ProductSeries(
                product_id=prod_retoma.id,
                serial=imei_retoma,
                estado='En Evaluación', # Va a cuarentena
                origen='retoma'
            )
            db.session.add(serie_retoma)

        db.session.commit()

        print("\n" + "=" * 60)
        print("  ✅ ÉXITO: VENTA INYECTADA CORRECTAMENTE")
        print("=" * 60)
        print(f"  Ticket N°    : #{nueva_venta.id}")
        print(f"  Cliente      : {nueva_venta.cliente_nombre}")
        print(f"  Total Venta  : ${monto_total:,.0f}")
        print(f"  -> Pagado en Efectivo : ${monto_efectivo:,.0f}")
        print(f"  -> Pagado en Retoma   : ${monto_retoma:,.0f}")
        print(f"  Equipo Retoma: {modelo_retoma} (IMEI: {imei_retoma})")
        print("=" * 60)
        print("  Este registro ya se encuentra monitoreado en tiempo real en:")
        print("  1. Historial de Operaciones: Nueva tarjeta 'Retoma' sumando $1,500,000.")
        print("  2. Inventario/Retomas: El iPhone 12 Pro en evaluación listo para auditar.")
        print("=" * 60)

if __name__ == '__main__':
    inyectar_ejemplo()
