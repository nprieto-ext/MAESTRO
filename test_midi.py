#!/usr/bin/env python3
"""Script de test pour vérifier l'installation MIDI"""

print("=" * 60)
print("TEST INSTALLATION MIDI POUR AKAI APC mini")
print("=" * 60)
print()

# Test 1: Import de rtmidi
print("1. Test import python-rtmidi...")
try:
    import rtmidi
    print("   ✅ python-rtmidi importé avec succès")
except ImportError as e:
    print(f"   ❌ Erreur import rtmidi: {e}")
    print()
    print("   Solution: Exécutez dans le terminal:")
    print("   py -m pip install python-rtmidi")
    print()
    input("Appuyez sur Entrée pour quitter...")
    exit(1)

print()

# Test 2: Lister les ports MIDI disponibles
print("2. Ports MIDI disponibles:")
print()

try:
    midi_in = rtmidi.MidiIn()
    midi_out = rtmidi.MidiOut()
    
    input_ports = midi_in.get_ports()
    output_ports = midi_out.get_ports()
    
    print(f"   Entrées MIDI ({len(input_ports)}):")
    if input_ports:
        for i, port in enumerate(input_ports, 1):
            marker = "   🎹 AKAI DÉTECTÉ!" if 'APC' in port.upper() or 'MINI' in port.upper() else ""
            print(f"      {i}. {port} {marker}")
    else:
        print("      Aucun port d'entrée MIDI trouvé")
    
    print()
    
    print(f"   Sorties MIDI ({len(output_ports)}):")
    if output_ports:
        for i, port in enumerate(output_ports, 1):
            marker = "   🎹 AKAI DÉTECTÉ!" if 'APC' in port.upper() or 'MINI' in port.upper() else ""
            print(f"      {i}. {port} {marker}")
    else:
        print("      Aucun port de sortie MIDI trouvé")
    
    print()
    
    # Test 3: Vérification AKAI
    print("3. Vérification AKAI APC mini:")
    akai_found = False
    for port in input_ports + output_ports:
        if 'APC' in port.upper() or 'MINI' in port.upper():
            akai_found = True
            break
    
    if akai_found:
        print("   ✅ AKAI APC mini détecté!")
        print("   Vous pouvez lancer le logiciel maestro.py")
    else:
        print("   ⚠️  AKAI APC mini non détecté")
        print()
        print("   Vérifiez que:")
        print("   - L'AKAI est branché via USB")
        print("   - Les drivers sont installés")
        print("   - L'appareil est allumé")
        print()
        if not input_ports and not output_ports:
            print("   ⚠️  Aucun périphérique MIDI trouvé du tout")
            print("   Il se peut que les drivers MIDI ne soient pas installés")
    
    midi_in.close_port()
    midi_out.close_port()
    
except Exception as e:
    print(f"   ❌ Erreur lors du test: {e}")

print()
print("=" * 60)
print("Test terminé!")
print("=" * 60)

input("\nAppuyez sur Entrée pour quitter...")

