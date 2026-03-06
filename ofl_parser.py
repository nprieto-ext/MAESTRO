"""
Parseur Open Fixture Library (OFL) pour MyStrow.

Formate les fixtures JSON du projet open-fixture-library en profils MyStrow.
API : parse_ofl_json(data, manufacturer_key, fixture_key, manufacturer_name) -> dict

Format OFL source :
  https://github.com/OpenLightingProject/open-fixture-library
"""

import json

# ---------------------------------------------------------------------------
# Mapping type de capability OFL -> type canal MyStrow
# ---------------------------------------------------------------------------

# Types simples (pas de propriété supplémentaire requise)
_SIMPLE_MAP = {
    "Intensity":        "Dim",
    "Pan":              "Pan",
    "PanContinuous":    "Pan",
    "Tilt":             "Tilt",
    "TiltContinuous":   "Tilt",
    "Zoom":             "Zoom",
    "Focus":            "Focus",
    "Iris":             "Iris",
    "Prism":            "Prism",
    "PrismRotation":    "Prism",
    "ShutterStrobe":    "Strobe",
    "StrobeSpeed":      "Strobe",
    "StrobeDuration":   "Strobe",
    "Speed":            "Speed",
    "EffectSpeed":      "Speed",
    "EffectDuration":   "Speed",
    "Rotation":         "Mode",
    "BeamAngle":        "Zoom",
    "BeamPosition":     "Mode",
    "Effect":           "Mode",
    "EffectParameter":  "Mode",
    "Fog":              "Mode",
    "FogOutput":        "Mode",
    "FogType":          "Mode",
    "Maintenance":      "Mode",
    "NoFunction":       "Mode",
    "Generic":          "Mode",
}

# ColorIntensity : dépend de la propriété "color"
_COLOR_MAP = {
    "Red":         "R",
    "Green":       "G",
    "Blue":        "B",
    "White":       "W",
    "WarmWhite":   "W",
    "ColdWhite":   "W",
    "Warm White":  "W",
    "Cold White":  "W",
    "Amber":       "Ambre",
    "UV":          "UV",
    "Cyan":        "Mode",
    "Magenta":     "Mode",
    "Yellow":      "Mode",
    "Lime":        "Mode",
    "Indigo":      "Mode",
}


def _get_channel_type(channel_name: str, channel_data: dict) -> str:
    """
    Déduit le type MyStrow pour un canal OFL.
    Utilise capability (singulier) ou le premier item de capabilities.
    """
    # capability singulier (un seul comportement)
    cap = channel_data.get("capability")
    if cap is None:
        caps = channel_data.get("capabilities", [])
        cap = caps[0] if caps else None

    if cap is None:
        return "Mode"

    cap_type = cap.get("type", "")

    if cap_type == "ColorIntensity":
        color = cap.get("color", "")
        return _COLOR_MAP.get(color, "Mode")

    if cap_type == "WheelSlot":
        # Roue couleur ou gobo selon le nom du canal
        name_lower = channel_name.lower()
        if "color" in name_lower or "colour" in name_lower or "cto" in name_lower:
            return "ColorWheel"
        # Par défaut gobo (Gobo1 / Gobo2 décidé plus haut selon l'index)
        return "Gobo"  # placeholder; résolu dans _map_channels

    return _SIMPLE_MAP.get(cap_type, "Mode")


def _map_channels(available: dict, mode_channels: list) -> list:
    """
    Construit le profil de canaux MyStrow pour un mode OFL.

    Gère :
    - Fine channels (fineChannelAliases sur le canal parent)
    - Gobo1 / Gobo2 selon l'ordre d'apparition
    - Canaux null (trou DMX) → "Mode"
    - Références matricielles (dict) → ignorées
    """
    # Pré-calcul : mapping fine_alias_name -> (parent_name, parent_mystrow)
    fine_aliases: dict[str, str] = {}  # alias_name -> parent_channel_name
    for ch_name, ch_data in available.items():
        for alias in ch_data.get("fineChannelAliases", []):
            fine_aliases[alias] = ch_name

    gobo_count = 0
    profile = []

    for ref in mode_channels:
        if ref is None:
            profile.append("Mode")
            continue
        if isinstance(ref, dict):
            # matrixChannels ou autre construction complexe → ignorer
            continue
        ch_name = str(ref)

        # Est-ce un alias fin ?
        if ch_name in fine_aliases:
            parent = fine_aliases[ch_name]
            parent_type = _get_channel_type(parent, available.get(parent, {}))
            if parent_type in ("Pan", "Tilt"):
                profile.append(parent_type + "Fine")
            else:
                profile.append("Mode")
            continue

        ch_data = available.get(ch_name, {})
        mtype = _get_channel_type(ch_name, ch_data)

        if mtype == "Gobo":
            gobo_count += 1
            profile.append("Gobo1" if gobo_count <= 1 else "Gobo2")
        else:
            profile.append(mtype)

    return profile


def _detect_fixture_type(profile: list) -> str:
    """Déduit le type de fixture depuis son profil."""
    if "Pan" in profile or "Tilt" in profile:
        return "Moving Head"
    return "PAR LED"


# ---------------------------------------------------------------------------
# API publique
# ---------------------------------------------------------------------------

def parse_ofl_json(
    data: bytes,
    manufacturer_key: str = "",
    fixture_key: str = "",
    manufacturer_name: str = "",
) -> dict:
    """
    Parse un fichier fixture OFL (bytes JSON) et retourne un dict MyStrow.

    Args:
        data:             Contenu brut du fichier JSON OFL
        manufacturer_key: Clé fabricant dans l'URL OFL (ex: "robe")
        fixture_key:      Clé fixture dans l'URL OFL (ex: "robin-600e-spot")
        manufacturer_name: Nom lisible du fabricant (ex: "Robe")

    Retourne:
        {
          "name": str,
          "manufacturer": str,
          "fixture_type": str,
          "source": "ofl",
          "uuid": str,
          "modes": [{"name": str, "channelCount": int, "profile": [str]}]
        }
    """
    try:
        obj = json.loads(data.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ValueError(f"JSON OFL invalide : {e}")

    name         = obj.get("name", fixture_key)
    # OFL n'a pas de clé manufacturer dans le JSON, on utilise le paramètre
    manufacturer = manufacturer_name or manufacturer_key

    available = obj.get("availableChannels", {})
    raw_modes  = obj.get("modes", [])

    modes = []
    for m in raw_modes:
        mode_name     = m.get("name") or m.get("shortName", f"Mode {len(modes)+1}")
        mode_channels = m.get("channels", [])
        profile       = _map_channels(available, mode_channels)
        modes.append({
            "name":         mode_name,
            "channelCount": len(profile),
            "profile":      profile,
        })

    if not modes:
        modes = [{"name": "Mode 1", "channelCount": 0, "profile": []}]

    first_profile = modes[0]["profile"] if modes else []
    ftype = _detect_fixture_type(first_profile)

    return {
        "name":         name,
        "manufacturer": manufacturer,
        "fixture_type": ftype,
        "source":       "ofl",
        "uuid":         f"ofl:{manufacturer_key}/{fixture_key}" if manufacturer_key else "",
        "modes":        modes,
    }
