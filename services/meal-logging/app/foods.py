"""Small food-related rules. They're plain functions with no database, so they're easy to test."""
import re
from dataclasses import dataclass

# What we tell people about how much we know about a food's nutrients
COMPLETE = "complete micronutrient data"
PARTIAL = "partial micronutrient data"
LABEL_ONLY = "label data only"


def confidence_label(data_type: str, has_full_micros: bool) -> str:
    """Branded foods only have what's on the label. Australian (AUSNUT) foods have every nutrient.
    The generic USDA foods usually have most, and has_full_micros (worked out by the data loader)
    says whether a food does."""
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


# Words about how food was cooked. The two data sets describe cooking differently (AUSNUT says
# "Rice, white, cooked", USDA says "boiled" or "steamed"), so we don't make these words appear in the
# name. We take them to mean "show cooked foods first" instead.
COOKING_WORDS = {"cooked", "boiled", "steamed", "baked", "grilled", "fried", "roasted", "roast", "poached",
                 "microwaved", "stewed", "braised", "bbq", "barbecued", "toasted", "scrambled", "sauteed"}


def stem(word: str) -> str:
    """Cut a plural ending off, so the word matches both forms: AUSNUT says "Banana", USDA says
    "Bananas". We keep the part both forms share, e.g. "strawberries" -> "strawberr", which is in
    "strawberry" and "strawberries", and "tomatoes" -> "tomato"."""
    if len(word) <= 3:
        return word
    if word.endswith("ies"):
        return word[:-3]
    if word.endswith(("oes", "ches", "shes", "xes")):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


@dataclass
class Search:
    """What someone searched for, worked out from what they typed."""
    words: list[str]            # words that must be in the food's name (plural endings cut off)
    state: str | None           # "raw" or "cooked" if they asked for one
    cooking_word: str | None    # e.g. "grilled", if they typed one
    all_words: list[str]        # every word they typed, in order (for names like "Baked beans")


def understand_search(query: str, state: str | None) -> Search:
    """Work out what someone is looking for.

    "rice boiled" needs "rice" in the name and prefers cooked foods. "bananas raw" needs "banana"
    and prefers raw ones. A raw/cooked choice made separately (the `state` setting) wins over
    words in the search.
    """
    words = search_words(query)
    cooking_word = next((w for w in words if w in COOKING_WORDS), None)
    if state is None:
        if "raw" in words:
            state = "raw"
        elif cooking_word:
            state = "cooked"
    kept = [w for w in words if w != "raw" and w not in COOKING_WORDS]
    if not kept:                      # someone just searched "fried": keep it as a normal word
        kept, cooking_word = words, None
    return Search([stem(w) for w in kept], state, cooking_word, [stem(w) for w in words])


def main_entry_pattern(words: list[str]) -> str:
    """A Postgres regular expression for names where these words are the whole first part, like
    "Banana, cavendish, raw" or "Bananas, raw" for "banana", or "Peanut butter, smooth" for
    "peanut butter". It doesn't match "Banana chip" or "Eggplant". Those main entries are usually
    what people mean. Only plural endings are allowed after each word."""
    parts = [re.sub(r"([^a-z0-9])", r"\\\1", w) + "(s|es|y|ies)?" for w in words]
    return "^" + r"\s+".join(parts) + "(,|$)"


def word_start_pattern(word: str) -> str:
    """A Postgres regular expression for a word that starts here, so "boiled" matches "hard-boiled"
    but not "parboiled", and "roast" matches "roasted". In Postgres, a backslash then "m" means
    "the start of a word"."""
    return r"\m" + re.sub(r"([^a-z0-9])", r"\\\1", word)


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
