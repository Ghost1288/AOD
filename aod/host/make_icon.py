"""Generates icon.ico for the Windows build from logo.png."""
from pathlib import Path
from PIL import Image

img = Image.open(Path(__file__).with_name("logo.png")).convert("RGBA")
img.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
