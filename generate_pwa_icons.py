import os
from PIL import Image

def generate_icons():
    logo_path = os.path.join('static', 'img', 'logo.png')
    out_dir = os.path.join('static', 'img', 'icons')
    if not os.path.exists(out_dir):
        os.makedirs(out_dir)

    logo = Image.open(logo_path).convert('RGBA')

    sizes = [
        ('icon-192.png', (192, 192)),
        ('icon-512.png', (512, 512)),
        ('apple-touch-icon.png', (180, 180)),
        ('favicon.png', (64, 64)),
    ]

    for name, size in sizes:
        # Crear un canvas cuadrado transparente
        canvas = Image.new('RGBA', size, (0, 0, 0, 0))
        # Escalar manteniendo la relación de aspecto dejando un margen del 10%
        target_w, target_h = int(size[0] * 0.85), int(size[1] * 0.85)
        logo_copy = logo.copy()
        logo_copy.thumbnail((target_w, target_h), Image.Resampling.LANCZOS)
        
        # Centrar el logo en el canvas
        offset_x = (size[0] - logo_copy.width) // 2
        offset_y = (size[1] - logo_copy.height) // 2
        canvas.paste(logo_copy, (offset_x, offset_y), logo_copy)

        out_path = os.path.join(out_dir, name)
        canvas.save(out_path, 'PNG')
        print(f"Icono generado: {out_path} ({size[0]}x{size[1]})")

if __name__ == '__main__':
    generate_icons()
