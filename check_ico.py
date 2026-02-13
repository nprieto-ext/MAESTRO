from PIL import Image

ico = Image.open("maestro.ico")

print("Tailles contenues dans l'ICO :")
print(ico.info.get("sizes"))