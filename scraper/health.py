"""Tag offers that matter to us: Magerquark, protein sources, fruit and vegetables.

Store sites don't publish nutrition data, so protein uses typical values per 100 g (approximate).
Adds to each offer: group, proteinPer100g, highProtein, pricePerKg, proteinPerChf, pick,
and compare/comparePrice/compareUnit for the cross-store "Bester Preis" comparison.
"""

import re

EGG_PROTEIN_G = 7  # one egg (53-63 g) has about 7 g protein
HIGH_PROTEIN_G = 10  # protein sticker from this many g per 100 g (Magerquark ≈ 12 g)
TOP_PROTEIN_PICKS = 3  # "Gucks dir an" for the best protein-per-franc deals

# Not food we want, even if a keyword matches (snacks, sweets, sauces, pasta, drinks...).
EXCLUDE = re.compile(
    r"chips|bonbon|lolli|schoko|praline|lindor|glace|kuchen|torte|guetzli|gebäck|backfüllung|sauce|"
    r"noodle|nudel|pasta|pappardelle|spaghetti|pizza|soda|sirup|saft|likör|wein|bier|tattoo|dekor|"
    r"kerze|seife|shampoo|duft|futter|katze|hund|vogel|samen|saatgut|topf|pflanze|strauch|zwiebel(n)? für|"
    r"spül|wasch|reinig|putz|entkalk|deo|lotion|kosmetik|"
    r"ramen|gyoza|instant|quick|fertiggericht|dumpling|"
    r"marzipan|berliner|börek|cracker|donut|croissant|feldschlösschen|alkoholfrei|radler|panaché|cider|"
    r"gratin|soss|dressing|quetschbeutel|babybrei|plastik|trinkbecher|halloween|pesto",
    re.I,
)

# Fruit & vegetables means fresh produce: not fruit yoghurt, jam, pickles, spices or ready meals.
EXCLUDE_FRESH = re.compile(
    r"drink|joghurt|jogurt|aufstrich|konfitüre|konfi\b|würz|gemahlen|teigplätzli|curry|käse|getrocknet|overnight|"
    r"knäcke|tofu|basilikum|scheiben|chirat|essig|eingelegt|konserve|püree|gehackte|ofengemüse|sirup|smoothie",
    re.I,
)

# (pattern, group, typical protein g/100 g or None). First match wins: specific before general.
RULES = [
    (r"protein.*(drink|milk|milch|shake)|(drink|milk|milch|shake).*(protein|skyr|quark)", "protein", 6),
    (r"magerquark", "magerquark", 12),
    (r"\bquark\b|speisequark", "protein", 9),
    (r"skyr", "protein", 11),
    (r"hüttenkäse|cottage", "protein", 12),
    (r"protein.*(pudding|milchreis|joghurt|jogurt|dessert)|(pudding|milchreis|joghurt|dessert).*protein", "protein", 10),
    (r"protein|high[- ]?protein", "protein", 20),
    (r"buschbohnen|grüne bohnen|stangenbohnen|bohnen mit speck|gemüsemischung|kefen|zuckerschoten", "gemuese", None),
    (r"nugget|paniert|knusperli|crunchy|croustillant|fischstäbchen|schlemmerfilet|cordon", "protein", 12),
    # whole chicken and legs are sold with bones: protein per 100 g bought, not per 100 g meat
    (r"^poulet(,|\s*$)|poulet.{0,3}ganz|ganzes poulet|bratbeutel|schenkel|schlegel|flügel|wings", "protein", 14),
    (r"poulet|hähnchen|huhn|truthahn|trute|geflügel", "protein", 23),
    (r"rinds?|rind\b|black angus|beef|steak|huft|filet|entrecôte|kalb", "protein", 21),
    (r"hackfleisch|gehacktes", "protein", 18),
    (r"schwein|kotelett|schnitzel", "protein", 20),
    (r"schinken|trockenfleisch|bündnerfleisch", "protein", 20),
    (r"lachs|thon|thunfisch|kabeljau|dorsch|forelle|crevette|garnele|fisch", "protein", 20),
    (r"\beier\b|\bei\b", "protein", 13),
    (r"tofu|tempeh|seitan", "protein", 15),
    (r"linsen|kichererbsen|bohnen|edamame", "protein", 9),
    (r"mandeln|nüsse|erdnüsse|cashew|baumnüsse", "protein", 20),
    (r"haferflocken|porridge|overnight oats", "protein", 9),
    (r"apfel|äpfel|birne|banane|\borangen?\b|mandarin|clementin|zitrone|kiwi|trauben|beeren|erdbeer|himbeer|"
     r"heidelbeer|ananas|mango|melone|pfirsich|nektarin|aprikos|zwetschg|pflaum|kirsche|granatapfel|früchte|obst",
     "frucht", None),
    (r"tomate|gurke|salat|rüebli|karotte|brokkoli|broccoli|blumenkohl|zucchetti|zucchini|peperoni|paprika|spinat|"
     r"kürbis|\blauch|sellerie|kohl|fenchel|aubergine|champignon|pilz|kartoffel|süsskartoffel|avocado|gemüse|randen",
     "gemuese", None),
]
RULES = [(re.compile(p, re.I), g, prot) for p, g, prot in RULES]

_UNIT = re.compile(r"CHF\s*([\d.']+)\s*/\s*([\d.]*)\s*(kg|g|l|ml|cl)\b", re.I)
_SIZE = re.compile(r"(?:(\d+)\s*[x×]\s*)?([\d.]+)\s*(kg|g|l|ml|cl)\b", re.I)  # "500 g", "2 x 140g"
_PER_KG = {"kg": 1, "l": 1, "g": 1000, "ml": 1000, "cl": 100}


def price_per_kg(offer):
    """CHF per kg (or litre) from price and pack size, else from the store's unit price.

    Price and size first: the stores round their unit price ("100g = 0.26"), which can hide a 2 % difference.
    """
    m = _SIZE.search((offer.get("size") or "").replace(",", "."))
    if m and offer.get("price"):
        qty, unit = float(m[1] or 1) * float(m[2]), m[3].lower()
        kg = qty / _PER_KG[unit]
        if kg:
            return round(offer["price"] / kg, 2)
    text = (offer.get("unitPriceDisplay") or "").replace("\xa0", " ")
    m = _UNIT.search(text)
    if m:
        chf, qty, unit = float(m[1].replace("'", "")), float(m[2] or 1), m[3].lower()
        return round(chf / qty * _PER_KG[unit], 2)
    return None


# Products we compare between stores: (key, pattern, exclusions, unit). Only plain, comparable
# products: no flavoured quark, no breaded chicken, no tomato sauce... Eggs are compared per piece.
COMPARE = [
    ("magerquark", r"magerquark",
     r"frucht|vanill|erdbeer|himbeer|zitron|schoko|mango|aprikos|heidel|kirsch|pfirsich|stracciatella|kräuter|"
     r"protein|drink|dessert|creme|crème|mousse", "kg"),
    ("eier", r"\beier\b|freilandeier|bodenhaltungseier|\bbio[- ]?eier",
     r"nudel|teigwar|likör|schoko|oster|gefärbt|gekocht|picknick|wachtel|salat|spätzl|hörnli|schwämm|"
     r"teig|pasta|cake|kuchen|nougat|trink|schachtel|karton", "stk"),
    ("pouletbrust", r"poulet[- ]?brust|pouletbrüstli|hähnchenbrust|hühnerbrust|poulet[- ]?schnitzel|poulet[- ]?filet",
     r"panier|nugget|cordon|aufschnitt|geräuch|wurst|gekocht|grilliert|knusper|mariniert|gewürzt|curry|kebab|"
     r"streifen|chicken|wings|flügel|schenkel|schlegel|salat|sandwich|wrap|snack|crispy|nuggets", "kg"),
    ("hackfleisch", r"hackfleisch|gehacktes",
     r"vegan|vegi|planted|pflanz|soja|erbs|tofu|lasagne|bällchen|burger|kebab|bolo|chili|cannelloni|poulet|trute", "kg"),
    ("aepfel", r"\bäpfel\b|\bapfel\b",
     r"mus|chips|ring|strudel|essig|schorle|tasche|wähe|getrocknet|püree|joghurt|quark|tee|crumble|kompott|"
     r"pfannkuchen|zimt|dörr|snack|riegel|chutney|gelee|konfi", "kg"),
    ("bananen", r"banane",
     r"chips|getrocknet|brot|joghurt|milch|shake|quark|split|smoothie|schoko|mus|püree|riegel|snack|dörr|drink", "kg"),
    ("rueebli", r"rüebli|karotte",
     r"salat|cake|püree|baby|suppe|chips|tiefk|erbsen", "kg"),
    ("kartoffeln", r"kartoffel",
     r"chips|stock|rösti|pommes|frites|gratin|krokett|salat|püree|wedges|gnocchi|suppe|knödel|puffer|süsskartoffel|"
     r"schnitz|tiefk|flocken|mehl|ofen", "kg"),
    ("tomaten", r"tomate",
     r"gehackt|püree|passat|getrocknet|konserv|pelati|ketchup|mozzarella|suppe|pesto|dose|cherry|cherr|datter|mini|"
     r"snack|cocktail|pizza|basilikum|frischkäse|gewürz|tofu|aufstrich|sugo", "kg"),
    ("broccoli", r"broccoli|brokkoli", r"tiefk|suppe|gratin|röschen|gefroren|mix", "kg"),
]
COMPARE = [(k, re.compile(p, re.I), re.compile(x, re.I), unit) for k, p, x, unit in COMPARE]
_PIECES = re.compile(r"(\d+)\s*(?:stück|stk\.?|er\b|er[- ]pack|eier)", re.I)


def compare_key(offer):
    """Which comparison product this offer is (e.g. "magerquark"), or None."""
    text = f"{offer.get('name') or ''} {offer.get('brand') or ''}"
    if offer.get("food") is False or EXCLUDE.search(text):
        return None, None
    for key, rx, exclude, unit in COMPARE:
        if rx.search(text):
            return (key, unit) if not exclude.search(text) else (None, None)
    return None, None


def is_staple(offer):
    """Regular-price products worth tracking every week: Magerquark and the comparison products."""
    return compare_key(offer)[0] is not None or bool(re.search("magerquark", offer.get("name") or "", re.I))


def compare_price(offer, unit, ppk):
    if unit == "kg":
        return ppk
    m = _PIECES.search(f"{offer.get('size') or ''} {offer.get('name') or ''}")
    return round(offer["price"] / int(m[1]), 2) if m and int(m[1]) and offer.get("price") else None


def classify(offer):
    text = f"{offer.get('name') or ''} {offer.get('brand') or ''}"
    if offer.get("food") is False or EXCLUDE.search(text):  # "food": set by stores that know (Lidl)
        return None, None
    for rx, group, protein in RULES:
        if rx.search(text):
            if group in ("frucht", "gemuese") and EXCLUDE_FRESH.search(text):
                return None, None
            return group, protein
    return None, None


def annotate(offers):
    for o in offers:
        group, protein = classify(o)
        exact = o.get("protein100g") is not None
        if exact:
            protein = o["protein100g"]
            group = group or ("protein" if protein >= HIGH_PROTEIN_G else None)
        ppk = price_per_kg(o)
        key, unit = compare_key(o)
        cmp_price = compare_price(o, unit, ppk) if key else None
        o.update(
            group=group,
            proteinPer100g=protein,
            proteinExact=exact,
            highProtein=bool(protein and protein >= HIGH_PROTEIN_G),
            pricePerKg=ppk,
            # grams of protein you get for 1 CHF (eggs sold by the piece: per egg)
            proteinPerChf=round(protein * 10 / ppk, 1) if protein and ppk else
            round(EGG_PROTEIN_G / cmp_price, 1) if key == "eier" and unit == "stk" and cmp_price else None,
            pick=group == "magerquark",
            compare=key if cmp_price else None,
            comparePrice=cmp_price,
            compareUnit=unit if cmp_price else None,
        )

    # Stickers go to this week's promotions only, not to regular prices tracked for the comparison.
    by_protein = sorted((o for o in offers if o["proteinPerChf"] and o["group"] == "protein" and not o["regular"]),
                        key=lambda o: -o["proteinPerChf"])
    for o in by_protein[:TOP_PROTEIN_PICKS]:
        o["pick"] = True
    for group in ("frucht", "gemuese"):
        cheapest = min((o for o in offers if o["group"] == group and o["pricePerKg"] and not o["regular"]),
                       key=lambda o: o["pricePerKg"], default=None)
        if cheapest:
            cheapest["pick"] = True
    return offers
