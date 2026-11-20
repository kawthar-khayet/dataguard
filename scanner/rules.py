"""
DataGuard — les règles de détection, réunies dans un seul fichier.

Pour ajouter un nouveau type de donnée sensible, il suffit de compléter ces dictionnaires :
le reste du scanner les utilise automatiquement.
"""
import re

# --- 1. Regex sur les VALEURS (formats fixes) --------------------------------
# Chaque regex doit couvrir la valeur ENTIÈRE d'une cellule (fullmatch).
VALUE_PATTERNS = {
    "CIN":     r"[A-Z]{1,2}\d{5,6}",                       # AB123456, J41234
    "PHONE":   r"(?:\+212|0)[5-7](?:\s?\d){8}",            # 0612345678, +212612345678, 06 12 34 56 78
    "EMAIL":   r"[\w.+-]+@[\w-]+\.[\w.-]+",
    "IBAN":    r"MA\d{26}",                                # IBAN marocain : 28 caractères
    "ADDRESS": r"\d+,?\s+(?:rue|avenue|av\.|bd|boulevard|impasse|chemin|allée|place|route)\b.*",
}
VALUE_REGEX = {t: re.compile(p, re.IGNORECASE if t == "ADDRESS" else 0)
               for t, p in VALUE_PATTERNS.items()}

# Les mêmes formats, mais cherchés À L'INTÉRIEUR d'un texte libre (search, pas fullmatch).
# \b = frontière de mot, pour ne pas trouver un "CIN" au milieu d'un autre mot.
TEXT_PATTERNS = {
    "CIN":   r"\b[A-Z]{1,2}\d{5,6}\b",
    "PHONE": r"(?:\+212|\b0)[5-7](?:\s?\d){8}\b",
    "EMAIL": VALUE_PATTERNS["EMAIL"],
    "IBAN":  r"\bMA\d{26}\b",
}

# --- 2. Mots-clés dans les NOMS de colonnes ---------------------------------
NAME_KEYWORDS = {
    "CIN":           ["cin", "cni", "carte_identite", "national_id"],
    "PHONE":         ["tel", "phone", "gsm", "mobile", "portable"],
    "EMAIL":         ["mail", "courriel"],
    "IBAN":          ["iban", "rib", "compte_bancaire"],
    "PERSON":        ["nom", "prenom", "name"],
    "DATE_OF_BIRTH": ["naissance", "birth", "dob"],
    "ADDRESS":       ["adresse", "address"],
}

# Règle contextuelle : ces mots dans le nom d'une colonne indiquent un code métier,
# pas une donnée personnelle → on baisse le score (ex. code_offre ressemble à un CIN).
NEGATIVE_KEYWORDS = ["code", "offre", "produit", "statut", "libelle", "canal", "segment", "mode"]

# --- 3. Classification : type → catégorie et niveau de sensibilité ----------
CLASSIFICATION = {
    "CIN":           ("Identité",   "Restreint"),
    "IBAN":          ("Financier",  "Restreint"),
    "PERSON":        ("Identité",   "Confidentiel"),
    "DATE_OF_BIRTH": ("Identité",   "Confidentiel"),
    "PHONE":         ("Contact",    "Confidentiel"),
    "EMAIL":         ("Contact",    "Confidentiel"),
    "ADDRESS":       ("Contact",    "Confidentiel"),
    "FREE_TEXT":     ("Texte libre", "Confidentiel"),
}

# --- 4. Politiques de protection proposées par type ---------------------------
# méthode de masquage → (exemple de résultat, explication)
MASKING = {
    "CIN":           ("HASH",           "SHA-256 : illisible, mais deux CIN identiques donnent le même code (jointures possibles)"),
    "IBAN":          ("PARTIAL_LAST4",  "MA************************1234 : seuls les 4 derniers chiffres restent visibles"),
    "PHONE":         ("PARTIAL_PHONE",  "06******78 : préfixe et 2 derniers chiffres visibles"),
    "EMAIL":         ("PARTIAL_EMAIL",  "a***@domaine.ma : le domaine reste utile pour l'analyse"),
    "PERSON":        ("REDACT",         "remplacé par [MASQUÉ]"),
    "ADDRESS":       ("REDACT",         "remplacé par [MASQUÉ] (la ville reste dans sa propre colonne)"),
    "DATE_OF_BIRTH": ("YEAR_ONLY",      "1997-10-18 → 1997 : permet de calculer des tranches d'âge"),
    "FREE_TEXT":     ("ANONYMIZE_TEXT", "les noms, CIN, téléphones… sont remplacés dans le texte par <PERSON>, <CIN>…"),
}

# niveau de sensibilité → rôles autorisés à voir la donnée EN CLAIR
# (tous les autres rôles, dont « analyst », ne voient que la version masquée)
CLEAR_ACCESS = {
    "Restreint":    ["dpo"],
    "Confidentiel": ["dpo", "support_client"],
}

# --- 5. Seuils de décision ------------------------------------------------------
THRESHOLD_PII = 0.7       # score >= 0.7  → donnée personnelle
THRESHOLD_REVIEW = 0.4    # 0.4 à 0.7     → à vérifier par un humain
FREE_TEXT_MIN_LENGTH = 40 # longueur moyenne au-delà de laquelle une colonne est du texte libre


def name_type(column_name: str) -> str | None:
    """Renvoie le type suggéré par le nom de la colonne, ou None."""
    name = column_name.lower()
    for pii_type, keywords in NAME_KEYWORDS.items():
        if any(k in name for k in keywords):
            return pii_type
    return None


def has_negative_keyword(column_name: str) -> bool:
    name = column_name.lower()
    return any(k in name for k in NEGATIVE_KEYWORDS)
