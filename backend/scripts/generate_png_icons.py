import os
from PIL import Image, ImageDraw

def render_logo(size: int) -> Image.Image:
    # Supersample at 4x for crystal clear anti-aliasing
    scale = 4
    canvas_size = size * scale
    vb = 96.0
    s = canvas_size / vb

    img = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 1. Rounded rectangle background (#4F46E5)
    r = 22 * s
    draw.rounded_rectangle([0, 0, canvas_size, canvas_size], radius=r, fill="#4F46E5")

    # 2. White arc "C": center (48, 48), radius 26, stroke-width 9
    # In SVG: path d="M69 33 A26 26 0 1 0 69 63"
    # Angle start: atan2(33-48, 69-48) = -35.22 deg (or 324.78 deg) to 35.22 deg clockwise
    # Bounding box for arc centered at 48*s: [(48-26)*s, (48-26)*s, (48+26)*s, (48+26)*s]
    arc_box = [(48 - 26) * s, (48 - 26) * s, (48 + 26) * s, (48 + 26) * s]
    # Arc from 35.22 deg clockwise to 324.78 deg (which is 35.22 to 360-35.22 = 324.78 deg)
    draw.arc(arc_box, start=35.22, end=324.78, fill="#FFFFFF", width=int(round(9 * s)))

    # 3. Checkmark (#10213A): stroke-width 8, points (41, 50) -> (50, 59) -> (72, 35)
    p1 = (41 * s, 50 * s)
    p2 = (50 * s, 59 * s)
    p3 = (72 * s, 35 * s)
    w = int(round(8 * s))

    draw.line([p1, p2, p3], fill="#10213A", width=w, joint="round")
    
    # Draw round caps at endpoints p1 and p3
    r_cap = w / 2.0
    draw.ellipse([p1[0]-r_cap, p1[1]-r_cap, p1[0]+r_cap, p1[1]+r_cap], fill="#10213A")
    draw.ellipse([p3[0]-r_cap, p3[1]-r_cap, p3[0]+r_cap, p3[1]+r_cap], fill="#10213A")

    # Downsample using Lanczos
    return img.resize((size, size), Image.Resampling.LANCZOS)

def generate():
    pub_dir = os.path.join(os.path.dirname(__file__), "..", "frontend", "public")
    assets_dir = os.path.join(pub_dir, "assets")
    os.makedirs(assets_dir, exist_ok=True)

    img_192 = render_logo(192)
    img_192.save(os.path.join(assets_dir, "icon-192.png"), "PNG")
    img_192.save(os.path.join(pub_dir, "icon-192.png"), "PNG")

    img_512 = render_logo(512)
    img_512.save(os.path.join(assets_dir, "icon-512.png"), "PNG")
    img_512.save(os.path.join(pub_dir, "icon-512.png"), "PNG")

    # Save favicon.ico (multi-resolution 32x32, 48x48, 64x64)
    img_64 = render_logo(64)
    img_64.save(os.path.join(pub_dir, "favicon.ico"), format="ICO", sizes=[(32, 32), (48, 48), (64, 64)])

    print("PNG and ICO icons generated successfully!")

if __name__ == "__main__":
    generate()
