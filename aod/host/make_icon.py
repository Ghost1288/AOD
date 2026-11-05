"""Generates icon.ico for the Windows build."""
from PIL import Image, ImageDraw

img = Image.new("RGBA", (256, 256), (11, 13, 18, 255))
d = ImageDraw.Draw(img)
d.ellipse((30, 30, 226, 226), outline=(74, 222, 128, 255), width=26)
d.ellipse((98, 98, 158, 158), fill=(74, 222, 128, 255))
img.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
