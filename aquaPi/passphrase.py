#!/usr/bin/env python3
""" random passphrase and token generation, used e.g. for the
    auto-generated default admin password.
"""

import logging
import secrets

log = logging.getLogger('aquaPi.passphrase')

WORDS = {
    "de": [
        "alge", "anemone", "barsch", "biber", "dorsch", "fisch", "frosch", "garnele", "hai",
        "hecht", "hering", "hummer", "karpfen", "koralle", "krabbe", "krebs", "krokodil", "lachs",
        "molch", "muschel", "otter", "polyp", "pinguin", "pottwal", "qualle", "robbe", "rochen",
        "schnecke", "schwamm", "seehund", "seestern", "stör", "thunfisch", "tintenfisch", "wal",
        "wels", "zander", "zattoo", "anabant", "guppy", "auge", "bauch", "fettflosse", "flosse",
        "kieme", "kropf", "maul", "panzer", "rücken", "saugnapf", "schnauze", "schuppe",
        "schwanz", "taster", "weich", "zahn", "zunge", "zwerg", "bunt", "muster", "farn", "fels",
        "glas", "grund", "hoehle", "holz", "kies", "kraut", "laub", "moos", "pflanze", "riff",
        "rohr", "sand", "stein", "strunk", "sumpf", "wurzel", "wrack", "zweig", "becken", "wand",
        "boden", "untergrund", "rand", "bach", "blau", "dampf", "druck", "eis", "flock", "fluss",
        "flussbed", "frisch", "frost", "gischt", "grad", "grün", "hafen", "kalt", "kälte", "klar",
        "kristall", "meer", "nass", "ozean", "perle", "quelle", "rein", "salz", "schaum", "säure",
        "schatten", "see", "stille", "strahl", "strom", "teich", "tiefe", "tropfen", "trüb",
        "ufer", "unterwasser", "warm", "wärme", "wasser", "welle", "wirbel", "zirkulieren",
        "zone", "eimer", "filter", "futter", "haken", "kabel", "kescher", "klemme", "kur", "lamp",
        "licht", "netz", "pumpe", "sauger", "schlauch", "sieb", "skimmer", "spachtel", "spueler",
        "stecker", "test", "timer", "tubus", "uhr", "ventil", "ventilator", "waage", "wolle",
        "zange", "zuleitung", "zulauf", "ablauf", "pflegemittel", "bürste", "abseihen",
        "abtauchen", "blubbern", "dampfen", "drift", "fließen", "fressen", "füttern", "gleiten",
        "glänzen", "jagen", "laichen", "leuchten", "perlen", "putzen", "reinigen", "rudern",
        "saugen", "schwimmen", "sinken", "spülen", "sprudeln", "spitzen", "steigen", "strömen",
        "tauchen", "treiben", "untergehen", "waten", "wechseln", "weiden", "wogend", "zucken",
        "züchten"
    ],
    "en": [
        "algae", "anemone", "angel", "bass", "clam", "coral", "crab", "guppy", "hermit", "kelp",
        "krill", "lobster", "manta", "minnow", "mollusk", "mussel", "otter", "oyster", "plankton",
        "polyp", "prawn", "puffer", "ray", "reef", "salmon", "scallop", "shark", "shrimp",
        "snail", "sponge", "squid", "starfish", "stingray", "tetra", "trout", "tuna", "turtle",
        "urchin", "whale", "zebra", "belly", "claw", "crest", "eyeball", "fag", "fang", "fin",
        "gill", "jaw", "mouth", "pincer", "scale", "shell", "snout", "spine", "tail", "tentacle",
        "tooth", "torso", "whiskers", "arch", "bark", "basin", "bed", "bottom", "branch",
        "bridge", "cave", "clay", "driftwood", "fern", "flora", "glass", "gravel", "grove",
        "hide", "moss", "pebble", "plant", "rock", "root", "sand", "stone", "tank", "wreck",
        "acid", "aqua", "blue", "bubble", "chill", "clear", "cold", "current", "deep", "depth",
        "dew", "drift", "foam", "fresh", "frost", "flow", "gulf", "heat", "ice", "lake", "liquid",
        "mist", "motion", "ocean", "peak", "pond", "pool", "pure", "rain", "river", "salt", "sea",
        "shade", "shine", "shore", "steam", "stream", "tide", "tint", "vapor", "warm", "water",
        "wave", "wet", "zone", "bucket", "cable", "clip", "cooler", "drain", "feed", "filter",
        "gauge", "grid", "heater", "hose", "hosing", "light", "mesh", "meter", "net", "nozzle",
        "pack", "pad", "pipe", "plug", "pump", "rack", "ring", "siphon", "skimmer", "spout",
        "strip", "swab", "tube", "valve", "wire", "clean", "dive", "drip", "float", "flush",
        "glide", "glow", "hatch", "hunt", "leak", "moult", "paddle", "peck", "pour", "rinse",
        "roam", "rush", "scour", "skim", "soak", "splash", "spray", "spurt", "swim", "swirl",
        "track", "wade", "wash"
    ]
}

DELIMITERS = ["-", "_", ".", "#", "!", "$", "+", "=", ":", "/"]


def generate_aquatic_passphrase(lang: str = "de") -> str:
    """ generate a human-readable, aquarium-themed passphrase, e.g.
        "shark-blue-42"
    """
    if lang not in WORDS:
        log.warning("Unknown passphrase language %r, falling back to 'en'", lang)
        lang = "en"

    word_pool = WORDS[lang]

    # 1. Zufällig 2 oder 3 Wörter wählen
    num_words = secrets.choice([2, 3])
    chosen_words = [secrets.choice(word_pool) for _ in range(num_words)]

    # 2. Zufällig entscheiden, ob eine Zahl angefügt wird (True/False)
    include_number = secrets.choice([True, False])
    if include_number:
        # Zahl von 0 bis 999 (1-3 Stellen)
        number = str(secrets.randbelow(1000))
        chosen_words.append(number)

    # 3. Ein einheitliches Trennzeichen wählen
    delimiter = secrets.choice(DELIMITERS)

    return delimiter.join(chosen_words)


def generate_url_token(nbytes: int = 32) -> str:
    """ generate an opaque, URL-safe random token (e.g. for reset links) """
    return secrets.token_urlsafe(nbytes)
