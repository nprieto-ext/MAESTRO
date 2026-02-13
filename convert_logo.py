from PIL import Image

img = Image.open("logo.png")

img.save(
    "maestro.ico",
    format="ICO",
    sizes=[(16,16),(32,32),(48,48),(64,64),(128,128),(256,256)]
)

print("ICO multi-tailles créé")