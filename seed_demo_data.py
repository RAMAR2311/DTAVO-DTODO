# -*- coding: utf-8 -*-
"""
Script para generar datos de demostración realistas en DTAVO
"""

import sys
import os
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from app import app
from models import (
    db, User, Category, Product, ProductSeries, ProductVariant,
    Customer, Provider, Expense, Sale, SaleDetail, SalePayment, ArqueoCaja
)

def poblar_datos_demo():
    with app.app_context():
        print("============================================================")
        print("INICIANDO POBLACION DE DATOS DEMO REALISTAS EN DTAVO")
        print("============================================================")

        # 1. USUARIOS / PERSONAL
        print("\n1. Verificando usuarios...")
        users_data = [
            {"nombre": "Administrador", "email": "admin@dtavo.com", "rol": "admin", "tel": "3001234567"},
            {"nombre": "Roberto Sánchez", "email": "roberto@dtavo.com", "rol": "vendedor", "tel": "3112345678"},
            {"nombre": "Camila Torres", "email": "camila@dtavo.com", "rol": "vendedor", "tel": "3209876543"},
            {"nombre": "Carlos Bodega", "email": "bodega@dtavo.com", "rol": "bodega", "tel": "3158765432"}
        ]
        users_map = {}
        for u in users_data:
            user = User.query.filter_by(email=u["email"]).first()
            if not user:
                user = User(
                    nombre=u["nombre"],
                    email=u["email"],
                    password_hash=generate_password_hash("123456"),
                    rol=u["rol"],
                    telefono=u["tel"]
                )
                db.session.add(user)
                db.session.commit()
                print(f"  [+] Usuario creado: {u['nombre']} ({u['rol']})")
            users_map[u["email"]] = user

        admin_user = users_map["admin@dtavo.com"]
        vendedor_user = users_map["roberto@dtavo.com"]

        # 2. CATEGORÍAS / NICHOS
        print("\n2. Verificando categorias / nichos...")
        cat_data = [
            ("Celulares", "Smartphones nuevos y seminuevos con serial/IMEI"),
            ("Ropa", "Prendas de vestir, camisetas, hoodies y pantalones con tallas"),
            ("Accesorios", "Cargadores, cables, audifonos y protectores"),
            ("Calzado", "Zapatos y zapatillas deportivas multimarca")
        ]
        cat_map = {}
        for nom, desc in cat_data:
            cat = Category.query.filter_by(nombre=nom).first()
            if not cat:
                cat = Category(nombre=nom, descripcion=desc)
                db.session.add(cat)
                db.session.commit()
                print(f"  [+] Categoria creada: {nom}")
            cat_map[nom] = cat

        # 3. CLIENTES POS
        print("\n3. Verificando clientes de mostrador...")
        clientes_data = [
            {"cedula": "000000000", "nombre": "Público General", "telefono": "3000000000", "correo": "general@dtavo.com"},
            {"cedula": "1037654321", "nombre": "Laura Restrepo", "telefono": "3114567890", "correo": "laura.restrepo@gmail.com"},
            {"cedula": "1020304050", "nombre": "Andrés Felipe Morales", "telefono": "3158901234", "correo": "afmorales@hotmail.com"},
            {"cedula": "1017894561", "nombre": "Valentina Ríos", "telefono": "3207654321", "correo": "vale.rios@outlook.com"},
            {"cedula": "71234567", "nombre": "Mateo Salazar", "telefono": "3009876543", "correo": "mateo.salazar@zenic.co"}
        ]
        clientes_map = {}
        for c in clientes_data:
            cust = Customer.query.filter_by(cedula=c["cedula"]).first()
            if not cust:
                cust = Customer(cedula=c["cedula"], nombre=c["nombre"], telefono=c["telefono"], correo=c["correo"])
                db.session.add(cust)
                db.session.commit()
                print(f"  [+] Cliente creado: {c['nombre']} ({c['cedula']})")
            clientes_map[c["cedula"]] = cust

        # 4. PROVEEDORES
        print("\n4. Verificando proveedores...")
        prov_data = [
            ("Global Tech Import S.A.S", "Global Tech", "3105551234"),
            ("Textiles & Moda Medellín", "Textiles Premium", "3004445678"),
            ("Accesorios Colombia Mayorista", "Accesorios Mayoristas", "3189998877")
        ]
        for nom, emp, tel in prov_data:
            prov = Provider.query.filter_by(nombre=nom).first()
            if not prov:
                prov = Provider(nombre=nom, empresa=emp, telefono=tel)
                db.session.add(prov)
                db.session.commit()
                print(f"  [+] Proveedor creado: {nom}")

        # 5. PRODUCTOS
        print("\n5. Verificando catalogo de productos...")
        
        # 5.1 Celulares (Serializados con IMEI)
        cel_cat = cat_map["Celulares"]
        prods_cel = [
            {
                "sku": "CEL-IP15PM-256",
                "nombre": "iPhone 15 Pro Max 256GB Titanio Natural",
                "costo": 3800000,
                "minimo": 4200000,
                "sugerido": 4500000,
                "seriales": ["357111222333444", "358999111222333", "354000111222333"]
            },
            {
                "sku": "CEL-S24U-512",
                "nombre": "Samsung Galaxy S24 Ultra 512GB Titanium Gray",
                "costo": 3600000,
                "minimo": 4000000,
                "sugerido": 4350000,
                "seriales": ["359812345678901", "359812345678902", "359812345678903"]
            },
            {
                "sku": "CEL-IP13-128",
                "nombre": "iPhone 13 128GB Midnight (Seminuevo 92% Bat)",
                "costo": 1700000,
                "minimo": 2000000,
                "sugerido": 2250000,
                "seriales": ["356123456789012", "356123456789013"]
            },
            {
                "sku": "CEL-RN13P-256",
                "nombre": "Xiaomi Redmi Note 13 Pro 256GB Black",
                "costo": 850000,
                "minimo": 1050000,
                "sugerido": 1200000,
                "seriales": ["351789456123456", "351789456123457", "351789456123458"]
            }
        ]

        for p_info in prods_cel:
            p = Product.query.filter_by(sku=p_info["sku"]).first()
            if not p:
                p = Product(
                    sku=p_info["sku"],
                    nombre=p_info["nombre"],
                    precio_costo=p_info["costo"],
                    precio_minimo=p_info["minimo"],
                    precio_sugerido=p_info["sugerido"],
                    es_serializado=True,
                    categoria_id=cel_cat.id,
                    atributos={"stock_minimo_alerta": 2, "Color": "Varios", "Capacidad": "256GB"}
                )
                db.session.add(p)
                db.session.commit()
                print(f"  [+] Celular creado: {p.nombre}")

            for s_num in p_info["seriales"]:
                serie = ProductSeries.query.filter_by(serial=s_num).first()
                if not serie:
                    serie = ProductSeries(product_id=p.id, serial=s_num, estado='disponible', origen='sistema')
                    db.session.add(serie)
            db.session.commit()

        # 5.2 Ropa (Con Variantes de Talla)
        ropa_cat = cat_map["Ropa"]
        prods_ropa = [
            {
                "sku": "ROP-TSHIRT-GOLD",
                "nombre": "Camiseta Oversize DTAVO Luxury Gold",
                "costo": 35000,
                "minimo": 65000,
                "sugerido": 79900,
                "variantes": [("S", 8), ("M", 15), ("L", 12), ("XL", 6)]
            },
            {
                "sku": "ROP-HOODIE-BLACK",
                "nombre": "Hoodie Heavyweight Cotton Black DTAVO",
                "costo": 65000,
                "minimo": 120000,
                "sugerido": 149000,
                "variantes": [("S", 5), ("M", 10), ("L", 8)]
            },
            {
                "sku": "ROP-CARGO-PANT",
                "nombre": "Pantalón Cargo Táctico Streetwear",
                "costo": 50000,
                "minimo": 95000,
                "sugerido": 119000,
                "variantes": [("30", 4), ("32", 7), ("34", 5)]
            }
        ]

        for p_info in prods_ropa:
            p = Product.query.filter_by(sku=p_info["sku"]).first()
            if not p:
                p = Product(
                    sku=p_info["sku"],
                    nombre=p_info["nombre"],
                    precio_costo=p_info["costo"],
                    precio_minimo=p_info["minimo"],
                    precio_sugerido=p_info["sugerido"],
                    es_serializado=False,
                    categoria_id=ropa_cat.id,
                    atributos={"stock_minimo_alerta": 5, "Material": "100% Algodón"}
                )
                db.session.add(p)
                db.session.commit()
                print(f"  [+] Prenda creada: {p.nombre}")

            for var_nom, var_stock in p_info["variantes"]:
                var = ProductVariant.query.filter_by(product_id=p.id, nombre_variante=var_nom).first()
                if not var:
                    var = ProductVariant(
                        product_id=p.id,
                        nombre_variante=var_nom,
                        cantidad_stock=var_stock,
                        precio_costo=p_info["costo"],
                        precio_minimo=p_info["minimo"],
                        precio_sugerido=p_info["sugerido"]
                    )
                    db.session.add(var)
            db.session.commit()

        # 5.3 Accesorios (Stock Plano)
        acc_cat = cat_map["Accesorios"]
        prods_acc = [
            {
                "sku": "ACC-CARG-35W",
                "nombre": "Cargador Rápido 35W Dual Type-C Apple/Android",
                "costo": 22000,
                "minimo": 45000,
                "sugerido": 59900,
                "stock": 25
            },
            {
                "sku": "ACC-AIRPODS-PRO",
                "nombre": "Audífonos Inalámbricos Pro 2da Gen ANC",
                "costo": 70000,
                "minimo": 140000,
                "sugerido": 175000,
                "stock": 14
            },
            {
                "sku": "ACC-CASE-MAGSAFE",
                "nombre": "Funda Silicona MagSafe Luxury Anti-Golpes",
                "costo": 12000,
                "minimo": 30000,
                "sugerido": 39900,
                "stock": 30
            },
            {
                "sku": "ACC-VIDRIO-9D",
                "nombre": "Protector Pantalla Vidrio Templado 9D HD",
                "costo": 3500,
                "minimo": 12000,
                "sugerido": 15000,
                "stock": 2
            }
        ]

        for p_info in prods_acc:
            p = Product.query.filter_by(sku=p_info["sku"]).first()
            if not p:
                p = Product(
                    sku=p_info["sku"],
                    nombre=p_info["nombre"],
                    precio_costo=p_info["costo"],
                    precio_minimo=p_info["minimo"],
                    precio_sugerido=p_info["sugerido"],
                    es_serializado=False,
                    categoria_id=acc_cat.id,
                    cantidad_stock=p_info["stock"],
                    atributos={"stock_minimo_alerta": 5}
                )
                db.session.add(p)
                db.session.commit()
                print(f"  [+] Accesorio creado: {p.nombre}")

        # 6. GASTOS DE DEMOSTRACIÓN
        print("\n6. Registrando gastos del mes actual y anterior...")
        now = datetime.now()
        gastos_data = [
            {"tipo": "Gasto Diario", "cat": "Alimentación", "desc": "Almuerzos de personal día sábado", "monto": 45000, "dias_atras": 1},
            {"tipo": "Gasto Diario", "cat": "Aseo y Mantenimiento", "desc": "Insumos de aseo y bolsas papel", "monto": 32000, "dias_atras": 3},
            {"tipo": "Gasto Diario", "cat": "Transporte / Fletes", "desc": "Flete entrega urgente domiciliario", "monto": 15000, "dias_atras": 4},
            {"tipo": "Costo Indirecto", "cat": "Internet / Teléfono", "desc": "Pago mensualidad Fibra Óptica Claro", "monto": 95000, "dias_atras": 7},
            {"tipo": "Costo Indirecto", "cat": "Servicios Públicos", "desc": "Energía EPM Local Comercial", "monto": 185000, "dias_atras": 10},
            {"tipo": "Costo Indirecto", "cat": "Arriendo", "desc": "Canon arriendo mes pasado", "monto": 1500000, "dias_atras": 35},
            {"tipo": "Costo Indirecto", "cat": "Servicios Públicos", "desc": "Energía y agua mes anterior", "monto": 178000, "dias_atras": 38},
            {"tipo": "Gasto Diario", "cat": "Alimentación", "desc": "Refrigerio equipo cierre quincena", "monto": 55000, "dias_atras": 40}
        ]

        for g in gastos_data:
            f_gasto = now - timedelta(days=g["dias_atras"])
            existe_gasto = Expense.query.filter_by(descripcion=g["desc"]).first()
            if not existe_gasto:
                exp = Expense(
                    usuario_id=admin_user.id,
                    tipo=g["tipo"],
                    categoria=g["cat"],
                    descripcion=g["desc"],
                    monto=g["monto"],
                    fecha=f_gasto
                )
                db.session.add(exp)
        db.session.commit()
        print("  [OK] Gastos de ejemplo registrados.")

        # 7. VENTAS DE DEMOSTRACIÓN (Históricas y del Mes Actual)
        print("\n7. Registrando ventas de demostración...")
        
        p_ip15 = Product.query.filter_by(sku="CEL-IP15PM-256").first()
        p_s24 = Product.query.filter_by(sku="CEL-S24U-512").first()
        p_ip13 = Product.query.filter_by(sku="CEL-IP13-128").first()
        p_tshirt = Product.query.filter_by(sku="ROP-TSHIRT-GOLD").first()
        p_hoodie = Product.query.filter_by(sku="ROP-HOODIE-BLACK").first()
        p_carg = Product.query.filter_by(sku="ACC-CARG-35W").first()
        p_airpods = Product.query.filter_by(sku="ACC-AIRPODS-PRO").first()
        p_case = Product.query.filter_by(sku="ACC-CASE-MAGSAFE").first()

        ventas_demo_configs = [
            # VENTA 1: Mes actual (Hace 2 horas)
            {
                "horas_atras": 2,
                "cliente": clientes_map["1037654321"],
                "vendedor": vendedor_user,
                "categoria_id": ropa_cat.id,
                "factura_fisica": "F-1021",
                "items": [
                    {"prod": p_tshirt, "var": p_tshirt.variantes[1] if p_tshirt.variantes else None, "cant": 2, "precio": 79900},
                    {"prod": p_case, "var": None, "cant": 1, "precio": 39900}
                ],
                "pagos": [
                    {"metodo": "efectivo", "monto": 100000},
                    {"metodo": "nequi", "monto": 99700}
                ]
            },
            # VENTA 2: Mes actual (Hace 1 día)
            {
                "horas_atras": 26,
                "cliente": clientes_map["1020304050"],
                "vendedor": admin_user,
                "categoria_id": cel_cat.id,
                "factura_fisica": "F-1020",
                "items": [
                    {
                        "prod": p_ip13,
                        "var": None,
                        "cant": 1,
                        "precio": 2200000,
                        "serial": "356123456789012",
                        "bateria": "92",
                        "estado": "Seminuevo",
                        "garantia": "6 Meses"
                    },
                    {"prod": p_carg, "var": None, "cant": 1, "precio": 50000}
                ],
                "pagos": [
                    {"metodo": "bancolombia", "monto": 2250000}
                ]
            },
            # VENTA 3: Mes actual (Hace 3 días)
            {
                "horas_atras": 74,
                "cliente": clientes_map["1017894561"],
                "vendedor": vendedor_user,
                "categoria_id": ropa_cat.id,
                "factura_fisica": None,
                "items": [
                    {"prod": p_hoodie, "var": p_hoodie.variantes[0] if p_hoodie.variantes else None, "cant": 1, "precio": 149000},
                    {"prod": p_tshirt, "var": p_tshirt.variantes[0] if p_tshirt.variantes else None, "cant": 1, "precio": 79900}
                ],
                "pagos": [
                    {"metodo": "tarjeta", "monto": 228900}
                ]
            },
            # VENTA 4: Mes actual (Hace 5 días)
            {
                "horas_atras": 120,
                "cliente": clientes_map["000000000"],
                "vendedor": vendedor_user,
                "categoria_id": acc_cat.id,
                "factura_fisica": None,
                "items": [
                    {"prod": p_airpods, "var": None, "cant": 1, "precio": 175000},
                    {"prod": p_carg, "var": None, "cant": 2, "precio": 59900}
                ],
                "pagos": [
                    {"metodo": "efectivo", "monto": 294800}
                ]
            },
            # VENTA 5: Mes actual (Hace 8 días)
            {
                "horas_atras": 190,
                "cliente": clientes_map["71234567"],
                "vendedor": admin_user,
                "categoria_id": cel_cat.id,
                "factura_fisica": "F-1018",
                "items": [
                    {
                        "prod": p_s24,
                        "var": None,
                        "cant": 1,
                        "precio": 4350000,
                        "serial": "359812345678902",
                        "bateria": "100",
                        "estado": "Nuevo",
                        "garantia": "1 Año"
                    }
                ],
                "pagos": [
                    {"metodo": "bancolombia", "monto": 4350000}
                ]
            },
            # VENTA 6: Mes Anterior (Hace 32 días)
            {
                "horas_atras": 32 * 24,
                "cliente": clientes_map["1037654321"],
                "vendedor": vendedor_user,
                "categoria_id": cel_cat.id,
                "factura_fisica": "F-0985",
                "items": [
                    {
                        "prod": p_ip15,
                        "var": None,
                        "cant": 1,
                        "precio": 4500000,
                        "serial": "358999111222333",
                        "bateria": "100",
                        "estado": "Nuevo",
                        "garantia": "1 Año"
                    }
                ],
                "pagos": [
                    {"metodo": "tarjeta", "monto": 4500000}
                ]
            },
            # VENTA 7: Mes Anterior (Hace 42 días)
            {
                "horas_atras": 42 * 24,
                "cliente": clientes_map["1020304050"],
                "vendedor": admin_user,
                "categoria_id": ropa_cat.id,
                "factura_fisica": "F-0950",
                "items": [
                    {"prod": p_tshirt, "var": p_tshirt.variantes[2] if p_tshirt.variantes else None, "cant": 3, "precio": 79900},
                    {"prod": p_hoodie, "var": p_hoodie.variantes[1] if p_hoodie.variantes else None, "cant": 2, "precio": 149000}
                ],
                "pagos": [
                    {"metodo": "efectivo", "monto": 537700}
                ]
            }
        ]

        total_consecutivo = Sale.query.count() + 1
        for cfg in ventas_demo_configs:
            f_venta = now - timedelta(hours=cfg["horas_atras"])
            total_monto = sum(it["cant"] * it["precio"] for it in cfg["items"])
            
            s = Sale(
                consecutivo=total_consecutivo,
                vendedor_id=cfg["vendedor"].id,
                cliente_nombre=cfg["cliente"].nombre,
                cliente_id=cfg["cliente"].id,
                categoria_id=cfg["categoria_id"],
                fecha_venta=f_venta,
                monto_total=total_monto,
                metodo_pago=cfg["pagos"][0]["metodo"] if len(cfg["pagos"]) == 1 else "mixto",
                factura_fisica=cfg["factura_fisica"]
            )
            db.session.add(s)
            db.session.flush()
            total_consecutivo += 1

            for it in cfg["items"]:
                det = SaleDetail(
                    sale_id=s.id,
                    product_id=it["prod"].id,
                    variant_id=it["var"].id if it["var"] else None,
                    cantidad_vendida=it["cant"],
                    precio_venta_final=it["precio"],
                    serial_vendido=it.get("serial"),
                    bateria=it.get("bateria"),
                    estado_producto=it.get("estado"),
                    tiempo_garantia=it.get("garantia")
                )
                db.session.add(det)
                db.session.flush()

                if it.get("serial"):
                    serie_obj = ProductSeries.query.filter_by(serial=it["serial"]).first()
                    if serie_obj:
                        serie_obj.estado = 'vendido'
                        serie_obj.sale_detail_id = det.id

            for p_info in cfg["pagos"]:
                sp = SalePayment(
                    sale_id=s.id,
                    metodo_pago=p_info["metodo"],
                    monto=p_info["monto"]
                )
                db.session.add(sp)

        db.session.commit()
        print("  [OK] 7 Ventas historicas y recientes registradas con exito.")

        print("\n============================================================")
        print("POBLACION DEMO COMPLETADA EXITOSAMENTE")
        print("============================================================")

if __name__ == "__main__":
    poblar_datos_demo()
