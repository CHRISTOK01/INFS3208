"""Small food-related rules. They're plain functions with no database, so they're easy to test."""

# What we tell people about how much we know about a food's nutrients
COMPLETE = "complete micronutrient data"
PARTIAL = "partial micronutrient data"
LABEL_ONLY = "label data only"


def confidence_label(data_type: str, has_full_micros: bool) -> str:
    """Branded foods only have what's on the label. The generic USDA foods usually have much more,
    and has_full_micros (worked out by the data loader) says whether a food has most of it."""
    if data_type == "branded_food":
        return LABEL_ONLY
    return COMPLETE if has_full_micros else PARTIAL


def to_grams(gram_weight: float, quantity: float) -> float:
    """Turn a household portion into grams. E.g. 2 x "1 cup" (30 g each) = 60 g.
    Grams are what we store, because that's what the nutrient maths needs."""
    return round(gram_weight * quantity, 2)


def search_words(query: str, max_words: int = 5) -> list[str]:
    """Split a search into words. Every word has to appear in the food's name, so "chicken breast"
    finds "Chicken, broilers or fryers, breast, meat only". Single letters are ignored."""
    words = []
    for word in query.lower().replace(",", " ").split():
        if len(word) >= 2 and word not in words:
            words.append(word)
    return words[:max_words]


def like_pattern(word: str) -> str:
    """Turn a word into a pattern for SQL's ILIKE, which is a "contains this, ignoring case" check.
    In ILIKE, % means "anything" and _ means "any one letter". If someone actually types % or _,
    we put a backslash in front so they're treated as normal characters."""
    escaped = word.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def starts_with_pattern(word: str) -> str:
    """An ILIKE pattern for names that start with the word."""
    return like_pattern(word)[1:]   # drop the % at the front


def first_of_each_name(rows: list[dict]) -> list[dict]:
    """Keep only the first food with each name (ignoring upper/lower case)."""
    seen = set()
    unique = []
    for row in rows:
        name = row["name"].lower()
        if name not in seen:
            seen.add(name)
            unique.append(row)
    return unique


def normalise_barcode(code: str) -> str:
    """Barcodes can come with or without zeros in front (0000020048556 vs 20048556), so we compare
    them with the leading zeros removed."""
    return code.strip().lstrip("0")
