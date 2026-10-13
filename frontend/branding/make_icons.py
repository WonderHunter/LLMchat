"""Génère les déclinaisons du logo à partir de logo-source.png.

Depuis la racine du projet :

    uv run --with pillow python frontend/branding/make_icons.py

Deux familles de fichiers sont écrites dans frontend/public :
- logo-mark.png : le dessin seul, utilisé comme masque CSS pour prendre la couleur du thème ;
- les icônes (favicon, écran d'accueil mobile) : le dessin clair sur un fond à la couleur d'accent.
"""

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
PUBLIC = HERE.parent / "public"

ACCENT = (201, 100, 66)  # --accent du thème clair
CREAM = (250, 249, 245)  # --bg du thème clair
SUPERSAMPLING = 4  # dessin en grand puis réduction, pour des bords lisses


def load_mark() -> Image.Image:
    """La transparence du dessin, recadrée au plus juste dans un carré."""
    alpha = Image.open(HERE / "logo-source.png").convert("RGBA").getchannel("A")
    left, top, right, bottom = alpha.getbbox()
    width, height = right - left, bottom - top
    side = max(width, height)
    square = Image.new("L", (side, side), 0)
    square.paste(alpha.crop((left, top, right, bottom)), ((side - width) // 2, (side - height) // 2))
    return square


def tinted(mark: Image.Image, size: int, color: tuple[int, int, int]) -> Image.Image:
    image = Image.new("RGBA", (size, size), (*color, 0))
    image.putalpha(mark.resize((size, size), Image.LANCZOS))
    return image


def tile(mark: Image.Image, size: int, *, radius: float, mark_ratio: float) -> Image.Image:
    """Le dessin clair, centré sur un carré à la couleur d'accent (coins arrondis si radius > 0)."""
    big = size * SUPERSAMPLING
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    ImageDraw.Draw(image).rounded_rectangle(
        (0, 0, big - 1, big - 1), radius=int(big * radius), fill=(*ACCENT, 255)
    )
    mark_size = int(big * mark_ratio)
    offset = (big - mark_size) // 2
    image.alpha_composite(tinted(mark, mark_size, CREAM), (offset, offset))
    return image.resize((size, size), Image.LANCZOS)


def main() -> None:
    mark = load_mark()
    outputs = {
        "logo-mark.png": tinted(mark, 256, (255, 255, 255)),
        "icon-192.png": tile(mark, 192, radius=0.22, mark_ratio=0.74),
        "icon-512.png": tile(mark, 512, radius=0.22, mark_ratio=0.74),
        # Plein cadre : iOS et Android appliquent leur propre découpe.
        "apple-touch-icon.png": tile(mark, 180, radius=0, mark_ratio=0.7),
        "icon-maskable-512.png": tile(mark, 512, radius=0, mark_ratio=0.56),
    }
    for name, image in outputs.items():
        image.save(PUBLIC / name, optimize=True)
        print(f"{name:24} {image.size[0]}x{image.size[1]}")

    favicon = tile(mark, 256, radius=0.22, mark_ratio=0.8)
    favicon.save(PUBLIC / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)])
    print(f"{'favicon.ico':24} 16, 32 et 48 px")


if __name__ == "__main__":
    main()
