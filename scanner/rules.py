"""
DataGuard — les règles de détection, réunies dans un seul fichier.

Pour ajouter un nouveau type de donnée sensible, il suffit de compléter ces dictionnaires :
le reste du scanner les utilise automatiquement.
"""
import re

# --- 0. Valeurs « vides déguisées » saisies par les agents ---------------------
# Ignorées par la détection : 5 % de « N/A » ne doivent pas faire baisser le score.
PLACEHOLDERS = {"", "n/a", "na", "inconnu", "-", "null", "none"}

# --- 1. Regex sur les VALEURS (formats fixes, y compris les saisies « sales ») ---
# Chaque regex doit couvrir la valeur ENTIÈRE d'une cellule (fullmatch).
VALUE_PATTERNS = {
    # AB123456, J41234, ab123456, « AB 123456 »
    "CIN":     r"[A-Za-z]{1,2}\s?\d{5,6}",
    # 0612345678, 06 12 34 56 78, 06.12.34.56.78, +212612345678, 212612345678
    "PHONE":   r"(?:\+?212[\s.-]?|0)[5-7](?:[\s.-]?\d){8}",
    "EMAIL":   r"[\w.+-]+@[\w-]+\.[\w.-]+",
    # IBAN marocain : MA + 26 chiffres, avec ou sans espaces tous les 4 caractères
    "IBAN":    r"MA(?:\s?\d){26}",
    "ADDRESS": r"\d+,?\s+(?:rue|avenue|av\.|bd|boulevard|impasse|chemin|allée|place|route)\b.*",
}
VALUE_REGEX = {t: re.compile(p, re.IGNORECASE if t in ("ADDRESS", "IBAN") else 0)
               for t, p in VALUE_PATTERNS.items()}

# Dates dans les formats rencontrés (pour reconnaître une date de naissance stockée en texte)
DATE_REGEX = re.compile(r"\d{4}-\d{2}-\d{2}.*|\d{2}/\d{2}/\d{4}|\d{2}-\d{2}-\d{2}")

# Les mêmes formats, mais cherchés À L'INTÉRIEUR d'un texte libre (search, pas fullmatch).
# \b = frontière de mot, pour ne pas trouver un "CIN" au milieu d'un autre mot.
TEXT_PATTERNS = {
    "CIN":   r"\b[A-Z]{1,2}\d{5,6}\b",
    "PHONE": r"(?:\+?212[\s.-]?|\b0)[5-7](?:[\s.-]?\d){8}\b",
    "EMAIL": VALUE_PATTERNS["EMAIL"],
    "IBAN":  r"\bMA(?:\s?\d){26}\b",
    # Le modèle NER français ne reconnaît pas les noms écrits en arabe au milieu
    # d'une phrase (constaté : 35 sur 41 oubliés). Règle de prudence : dans une base
    # rédigée en français, une suite de mots en alphabet arabe est traitée comme un nom.
    "PERSON_AR": r"[؀-ۿ]+(?:\s+[؀-ۿ]+)+",
}

# --- 2. Mots-clés dans les NOMS de colonnes ---------------------------------
# Comparés au DÉBUT de chaque mot du nom (« date_naiss » → « date », « naiss »).
NAME_KEYWORDS = {
    "CIN":           ["cin", "cni", "national"],
    "PHONE":         ["tel", "phone", "gsm", "mobile", "portable", "msisdn"],
    "EMAIL":         ["mail", "email", "courriel"],
    "IBAN":          ["iban", "rib"],
    "PERSON":        ["nom", "prenom", "name"],
    "DATE_OF_BIRTH": ["naiss", "birth", "dob"],
    "ADDRESS":       ["adr", "address"],
}

# Données de localisation : sensibles seulement quand elles sont liées à une personne
# (une antenne seule est publique ; « tel abonné + antenne + heure » = où était quelqu'un).
LOCATION_KEYWORDS = ["cell", "antenne", "lat", "lon", "gps", "localisation"]

# Règle contextuelle : ces mots dans le nom d'une colonne indiquent un code métier,
# pas une donnée personnelle → on baisse le score (ex. code_offre ressemble à un CIN).
NEGATIVE_KEYWORDS = ["code", "offre", "produit", "statut", "libelle", "canal", "segment", "mode"]

# --- 3. Classification : type → catégorie et niveau de sensibilité ----------
CLASSIFICATION = {
    "CIN":           ("Identité",     "Restreint"),
    "IBAN":          ("Financier",    "Restreint"),
    "PERSON":        ("Identité",     "Confidentiel"),
    "DATE_OF_BIRTH": ("Identité",     "Confidentiel"),
    "PHONE":         ("Contact",      "Confidentiel"),
    "EMAIL":         ("Contact",      "Confidentiel"),
    "ADDRESS":       ("Contact",      "Confidentiel"),
    "LOCATION":      ("Localisation", "Restreint"),     # suivre les déplacements d'une personne
    # Un texte libre peut contenir N'IMPORTE QUELLE donnée (CIN, IBAN…) :
    # on lui donne le niveau le plus élevé de ce qu'il peut contenir.
    "FREE_TEXT":     ("Texte libre",  "Restreint"),
}

# --- 4. Politiques de protection ---------------------------------------------------
# Couche « marts » (exposée aux analystes) → masquage colonne par colonne.
MASKING = {
    "CIN":           ("HASH",           "SHA-256 : illisible, mais deux CIN identiques donnent le même code (jointures possibles)"),
    "IBAN":          ("PARTIAL_LAST4",  "MA************************1234 : seuls les 4 derniers chiffres restent visibles"),
    "PHONE":         ("PARTIAL_PHONE",  "06******78 : préfixe et 2 derniers chiffres visibles"),
    "EMAIL":         ("PARTIAL_EMAIL",  "a***@domaine.ma : le domaine reste utile pour l'analyse"),
    "PERSON":        ("REDACT",         "remplacé par [MASQUÉ]"),
    "ADDRESS":       ("REDACT",         "remplacé par [MASQUÉ] (la ville reste dans sa propre colonne)"),
    "LOCATION":      ("REDACT",         "remplacé par [MASQUÉ]"),
    "DATE_OF_BIRTH": ("YEAR_ONLY",      "1997-10-18 → 1997 : permet de calculer des tranches d'âge"),
    "FREE_TEXT":     ("ANONYMIZE_TEXT", "les noms, CIN, téléphones… sont remplacés dans le texte par <PERSON>, <CIN>…"),
}

# Couches techniques (crm, raw, staging) → jamais exposées : restriction d'accès.
EXPOSED_LAYERS = {"marts"}
RESTRICT = ("RESTRICT_ACCESS", "couche technique : jamais exposée aux analystes, "
            "accès réservé aux rôles data_engineer et dpo (droits PostgreSQL)")
RESTRICTED_ROLES = ["data_engineer", "dpo"]

# niveau de sensibilité → rôles autorisés à voir la donnée EN CLAIR dans les marts
# (tous les autres rôles, dont « analyst », ne voient que la version masquée)
CLEAR_ACCESS = {
    "Restreint":    ["dpo"],
    "Confidentiel": ["dpo", "support_client"],
}

# --- 5. Seuils de décision ------------------------------------------------------
THRESHOLD_PII = 0.7       # score >= 0.7  → donnée personnelle
THRESHOLD_REVIEW = 0.4    # 0.4 à 0.7     → à vérifier par un humain
FREE_TEXT_MIN_LENGTH = 40 # longueur moyenne au-delà de laquelle une colonne est du texte libre


def _tokens(column_name: str) -> list[str]:
    return [t for t in re.split(r"[_\W]+", column_name.lower()) if t]


def name_type(column_name: str) -> str | None:
    """Renvoie le type suggéré par le nom de la colonne, ou None."""
    tokens = _tokens(column_name)
    for pii_type, keywords in NAME_KEYWORDS.items():
        if any(t.startswith(k) for t in tokens for k in keywords):
            return pii_type
    return None


def is_location_name(column_name: str) -> bool:
    return any(t.startswith(k) for t in _tokens(column_name) for k in LOCATION_KEYWORDS)


def has_negative_keyword(column_name: str) -> bool:
    return any(t.startswith(k) for t in _tokens(column_name) for k in NEGATIVE_KEYWORDS)


def is_placeholder(value: str) -> bool:
    return value.strip().lower() in PLACEHOLDERS
