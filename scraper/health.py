"""Tag offers that matter to us: Magerquark, protein sources, fruit and vegetables.

Store sites don't publish nutrition data, so protein uses typical values per 100 g (approximate).
Adds to each offer: group, proteinPer100g, highProtein, pricePerKg, proteinPerChf, pick.
"""

import re

HIGH_PROTEIN_G = 10  # protein sticker from this many g per 100 g (Magerquark ≈ 12 g)
TOP_PROTEIN_PICKS = 3  # "Gucks dir an" for the best protein-per-franc deals

# Not food we want, even if a keyword matches (snacks, sweets, sauces, pasta, drinks...).
EXCLUDE = re.compile(
    r"chips|bonbon|lolli|schoko|praline|lindor|glace|kuchen|torte|guetzli|gebäck|backfüllung|sauce|"
    r"noodle|nudel|pasta|pappardelle|spaghetti|pizza|soda|sirup|saft|likör|wein|bier|tattoo|dekor|"
    r"kerze|seife|shampoo|duft|futter|katze|hund|vogel|samen|saatgut|topf|pflanze|strauch|zwiebel(n)? für|"
    r"spül|wasch|reinig|putz|entkalk|deo|lotion|kosmetik|"
    r"ramen|gyoza|instant|quick|fertiggericht|dumpling",
    re.I,
)

# (pattern, group, typical protein g/100 g or None). First match wins: specific before general.
RULES = [
    (r"magerquark", "magerquark", 12),
    (r"\bquark\b|speisequark", "protein", 9),
    (r"skyr", "protein", 11),
    (r"hüttenkäse|cottage", "protein", 12),
    (r"protein|high[- ]?protein", "protein", 20),
    (r"poulet|hähnchen|huhn|truthahn|trute|geflügel", "protein", 23),
    (r"rinds?|rind\b|black angus|beef|steak|huft|filet|entrecôte|kalb", "protein", 21),
    (r"hackfleisch|gehacktes", "protein", 18),
    (r"schwein|kotelett|schnitzel", "protein", 20),
    (r"lachs|thon|thunfisch|kabeljau|dorsch|forelle|crevette|garnele|fisch", "protein", 20),
    (r"\beier\b|\bei\b", "protein", 13),
    (r"tofu|tempeh|seitan", "protein", 15),
    (r"linsen|kichererbsen|bohnen|edamame", "protein", 9),
    (r"mandeln|nüsse|erdnüsse|cashew|baumnüsse", "protein", 20),
    (r"haferflocken|porridge|overnight oats", "protein", 9),
    (r"apfel|äpfel|birne|banane|orange|mandarin|clementin|zitrone|kiwi|trauben|beeren|erdbeer|himbeer|"
     r"heidelbeer|ananas|mango|melone|pfirsich|nektarin|aprikos|zwetschg|pflaum|kirsche|granatapfel|früchte|obst",
     "frucht", None),
    (r"tomate|gurke|salat|rüebli|karotte|brokkoli|blumenkohl|zucchetti|zucchini|peperoni|paprika|spinat|"
     r"kürbis|lauch|sellerie|kohl|fenchel|aubergine|champignon|pilz|kartoffel|süsskartoffel|avocado|gemüse|randen",
     "gemuese", None),
]
RULES = [(re.compile(p, re.I), g, prot) for p, g, prot in RULES]

_UNIT = re.compile(r"CHF\s*([\d.']+)\s*/\s*([\d.]*)\s*(kg|g|l|ml|cl)\b", re.I)
_SIZE = re.compile(r"([\d.]+)\s*(kg|g|l|ml|cl)\b", re.I)
_PER_KG = {"kg": 1, "l": 1, "g": 1000, "ml": 1000, "cl": 100}


def price_per_kg(offer):
    """CHF per kg (or litre) from the store's unit price, else from price and pack size."""
    text = (offer.get("unitPriceDisplay") or "").replace("\xa0", " ")
    m = _UNIT.search(text)
    if m:
        chf, qty, unit = float(m[1].replace("'", "")), float(m[2] or 1), m[3].lower()
        return round(chf / qty * _PER_KG[unit], 2)
    m = _SIZE.search((offer.get("size") or "").replace(",", "."))
    if m and offer.get("price"):
        qty, unit = float(m[1]), m[2].lower()
        kg = qty / _PER_KG[unit]
        return round(offer["price"] / kg, 2) if kg else None
    return None


def classify(offer):
    text = f"{offer.get('name') or ''} {offer.get('brand') or ''}"
    if EXCLUDE.search(text):
        return None, None
    for rx, group, protein in RULES:
        if rx.search(text):
            return group, protein
    return None, None


def annotate(offers):
    for o in offers:
        group, protein = classify(o)
        ppk = price_per_kg(o)
        o.update(
            group=group,
            proteinPer100g=protein,
            highProtein=bool(protein and protein >= HIGH_PROTEIN_G),
            pricePerKg=ppk,
            # grams of protein you get for 1 CHF
            proteinPerChf=round(protein * 10 / ppk, 1) if protein and ppk else None,
            pick=group == "magerquark",
        )

    by_protein = sorted((o for o in offers if o["proteinPerChf"] and o["group"] == "protein"),
                        key=lambda o: -o["proteinPerChf"])
    for o in by_protein[:TOP_PROTEIN_PICKS]:
        o["pick"] = True
    for group in ("frucht", "gemuese"):
        cheapest = min((o for o in offers if o["group"] == group and o["pricePerKg"]),
                       key=lambda o: o["pricePerKg"], default=None)
        if cheapest:
            cheapest["pick"] = True
    return offers
