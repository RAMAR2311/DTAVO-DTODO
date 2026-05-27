# -*- coding: utf-8 -*-
"""
Script de prueba: Simula una venta con IMEI en categoria Celulares
y verifica que el query del dashboard los devuelva correctamente.
"""
import sys
import io
# Forzar UTF-8 en la salida de la consola Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

import os
os.environ['SESSION_COOKIE_SECURE'] = 'False'  # Evitar error SSL en local

from app import create_app
from models import db, User, Product, ProductSeries, Sale, SaleDetail, SalePayment, Category, obtener_hora_bogota
from werkzeug.security import generate_password_hash
from decimal import Decimal

def run_test():
    app = create_app()
    # Deshabilitar SSL en cookies para prueba local
    app.config['SESSION_COOKIE_SECURE'] = False

    with app.app_context():
        print("=" * 60)
        print("  TEST: Venta de ejemplo con IMEI (Trazabilidad Dashboard)")
        print("=" * 60)

        # ── 1. VERIFICAR / CREAR CATEGORÍA CELULARES ─────────────────
        cat = Category.query.filter(
            Category.nombre.ilike('%celular%')
        ).first()

        if not cat:
            # Buscar por ID 1 (default del POS)
            cat = Category.query.get(1)

        if not cat:
            cat = Category(nombre='Celulares', descripcion='Smartphones y accesorios serializados')
            db.session.add(cat)
            db.session.commit()
            print(f"[CREADO] Categoría: '{cat.nombre}' (ID: {cat.id})")
        else:
            print(f"[OK] Categoría encontrada: '{cat.nombre}' (ID: {cat.id})")

        # ── 2. VERIFICAR / CREAR PRODUCTO SERIALIZADO ─────────────────
        producto = Product.query.filter_by(sku='TEST-CEL-S24').first()
        if not producto:
            producto = Product(
                nombre='Samsung Galaxy S24 (TEST)',
                sku='TEST-CEL-S24',
                tipo_inventario='tienda',
                es_serializado=True,
                categoria_id=cat.id,
                precio_costo=Decimal('1800000'),
                precio_minimo=Decimal('2200000'),
                precio_sugerido=Decimal('2500000')
            )
            db.session.add(producto)
            db.session.commit()
            print(f"[CREADO] Producto: '{producto.nombre}' (ID: {producto.id})")
        else:
            print(f"[OK] Producto encontrado: '{producto.nombre}' (ID: {producto.id})")

        # ── 3. VERIFICAR / CREAR SERIAL (IMEI) DISPONIBLE ────────────
        imei_test = '359812345678901'
        serie = ProductSeries.query.filter_by(serial=imei_test).first()
        if not serie:
            serie = ProductSeries(
                product_id=producto.id,
                serial=imei_test,
                estado='disponible',
                origen='sistema'
            )
            db.session.add(serie)
            db.session.commit()
            print(f"[CREADO] Serial/IMEI: {imei_test} -> estado: disponible")
        else:
            if serie.estado != 'disponible':
                serie.estado = 'disponible'
                serie.sale_detail_id = None
                db.session.commit()
                print(f"[RESET] Serial {imei_test} -> estado reseteado a disponible")
            else:
                print(f"[OK] Serial encontrado: {imei_test} -> estado: {serie.estado}")

        # ── 4. OBTENER USUARIO VENDEDOR ───────────────────────────────
        vendedor = User.query.filter_by(rol='admin').first()
        if not vendedor:
            vendedor = User.query.first()
        print(f"[OK] Vendedor: '{vendedor.nombre}' (ID: {vendedor.id}, rol: {vendedor.rol})")

        # ── 5. REGISTRAR LA VENTA ─────────────────────────────────────
        precio_venta = Decimal('2450000')

        nueva_venta = Sale()
        nueva_venta.vendedor_id = vendedor.id
        nueva_venta.cliente_nombre = 'Cliente Test IMEI'
        nueva_venta.monto_total = precio_venta
        nueva_venta.metodo_pago = 'efectivo'
        nueva_venta.categoria_id = cat.id
        nueva_venta.fecha_venta = obtener_hora_bogota()
        db.session.add(nueva_venta)
        db.session.flush()

        # ── 6. REGISTRAR EL DETALLE CON EL SERIAL ────────────────────
        detalle = SaleDetail()
        detalle.sale_id = nueva_venta.id
        detalle.product_id = producto.id
        detalle.variant_id = None
        detalle.cantidad_vendida = 1
        detalle.precio_venta_final = precio_venta
        detalle.serial_vendido = imei_test
        detalle.bateria = '95%'
        detalle.estado_producto = 'Nuevo'
        detalle.tiempo_garantia = '12 meses'
        db.session.add(detalle)
        db.session.flush()

        # ── 7. MARCAR EL SERIAL COMO VENDIDO ─────────────────────────
        serie.estado = 'vendido'
        serie.sale_detail_id = detalle.id
        db.session.add(serie)

        # ── 8. REGISTRAR PAGO ─────────────────────────────────────────
        pago = SalePayment()
        pago.sale_id = nueva_venta.id
        pago.metodo_pago = 'efectivo'
        pago.monto = precio_venta
        db.session.add(pago)

        db.session.commit()
        print(f"\n[✓] VENTA REGISTRADA:")
        print(f"    Sale ID    : {nueva_venta.id}")
        print(f"    Detalle ID : {detalle.id}")
        print(f"    Serial ID  : {serie.id}")
        print(f"    IMEI       : {imei_test}")
        print(f"    Precio     : ${precio_venta:,.0f}")
        print(f"    Categoría  : {cat.nombre} (ID: {cat.id})")

        # ── 9. SIMULAR EL QUERY DEL DASHBOARD ────────────────────────
        print("\n" + "-" * 60)
        print("  VERIFICANDO query del dashboard (ultimos_imeis)...")
        print("-" * 60)

        ultimos_imeis = (
            db.session.query(ProductSeries, SaleDetail, Sale)
            .join(SaleDetail, ProductSeries.sale_detail_id == SaleDetail.id)
            .join(Sale, SaleDetail.sale_id == Sale.id)
            .filter(
                ProductSeries.estado == 'vendido',
                Sale.categoria_id == cat.id
            )
            .order_by(Sale.fecha_venta.desc())
            .limit(5)
            .all()
        )

        if ultimos_imeis:
            print(f"\n[✓] ÉXITO — {len(ultimos_imeis)} IMEI(s) encontrados en el dashboard:\n")
            print(f"  {'PRODUCTO':<35} {'IMEI/SERIAL':<20} {'PRECIO VENTA':>15}")
            print(f"  {'-'*35} {'-'*20} {'-'*15}")
            for s, d, v in ultimos_imeis:
                print(f"  {s.producto.nombre:<35} {s.serial:<20} ${float(d.precio_venta_final):>14,.0f}")
        else:
            print("\n[✗] ERROR — No se encontraron IMEIs. Revisa la categoría o el join.")

        # ── 10. VERIFICAR MODO CELULAR ────────────────────────────────
        print("\n" + "-" * 60)
        CATEGORIAS_CELULAR_IDS = {1, 6}
        es_modo_celular = cat.id in CATEGORIAS_CELULAR_IDS or 'celular' in cat.nombre.lower()
        estado = "✓ ACTIVO" if es_modo_celular else "✗ INACTIVO"
        print(f"  Modo Celular (cat ID={cat.id}, nombre='{cat.nombre}'): {estado}")
        print("=" * 60)
        print("  Test completado." + (" El dashboard debería mostrar los IMEIs." if ultimos_imeis else " Hay un problema, revisa arriba."))
        print("=" * 60)

if __name__ == '__main__':
    run_test()
