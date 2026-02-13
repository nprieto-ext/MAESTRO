import mido

# Trouver l'APC Mini MK2
name = next(n for n in mido.get_input_names() if "APC" in n)
print("🎹 Utilisation du port :", name)
print("👉 Appuyez sur des PADS (Ctrl+C pour quitter)\n")

with mido.open_input(name) as port:
    for msg in port:
        print(msg)
