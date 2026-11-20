"""
DataGuard — étape 2 du scanner : détection et classification.

Pour chaque colonne profilée, trois sources d'indices sont combinées :
  1. regex sur les valeurs      → formats fixes (CIN, téléphone, IBAN, e-mail, adresse)
  2. NLP (Presidio + spaCy NER) → noms de personnes, et données personnelles dans le texte libre
  3. nom de la colonne          → mots-clés positifs (bonus) et négatifs (malus)
Le résultat : un type, une catégorie, un niveau de sensibilité, un score de confiance
et une décision (PII / À vérifier / Non sensible).
"""
import logging
from dataclasses import dataclass
from functools import lru_cache

from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
from presidio_analyzer.nlp_engine import NlpEngineProvider

from scanner import rules
from scanner.discovery import ColumnProfile

logging.getLogger("presidio-analyzer").setLevel(logging.ERROR)

W_VALUES = 0.7       # poids des indices tirés des valeurs
W_NAME = 0.3         # bonus si le nom de colonne confirme le type
MALUS_NEGATIVE = 0.3 # malus si le nom de colonne évoque un code métier


@dataclass
class Detection:
    table_name: str
    column_name: str
    pii_type: str | None
    category: str | None
    sensitivity: str
    confidence: float
    decision: str      # "PII", "À vérifier", "Non sensible"
    evidence: str      # explication lisible : pourquoi ce résultat


# --- Moteur NLP --------------------------------------------------------------------
@lru_cache(maxsize=1)
def analyzer() -> AnalyzerEngine:
    """Presidio en français, chargé une seule fois (le modèle spaCy prend quelques secondes)."""
    nlp = NlpEngineProvider(nlp_configuration={
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "fr", "model_name": "fr_core_news_md"}],
    }).create_engine()
    engine = AnalyzerEngine(nlp_engine=nlp, supported_languages=["fr"])
    # On apprend à Presidio les formats marocains, pour les retrouver dans le texte libre.
    for pii_type, pattern in rules.TEXT_PATTERNS.items():
        engine.registry.add_recognizer(PatternRecognizer(
            supported_entity=f"MA_{pii_type}", supported_language="fr",
            patterns=[Pattern(name=pii_type, regex=pattern, score=0.9)]))
    return engine


def is_person_name(value: str) -> bool:
    """Vrai si le NER reconnaît une personne qui couvre presque toute la valeur."""
    for r in analyzer().analyze(value, language="fr", entities=["PERSON"]):
        if (r.end - r.start) >= 0.8 * len(value.strip()):
            return True
    return False


def text_entities(value: str) -> set[str]:
    """Types de données personnelles trouvés dans un texte libre."""
    wanted = ["PERSON"] + [f"MA_{t}" for t in rules.TEXT_PATTERNS]
    return {r.entity_type for r in analyzer().analyze(value, language="fr", entities=wanted)}


# --- Détection d'une colonne ---------------------------------------------------------
def detect(col: ColumnProfile) -> Detection:
    sample = [v.strip() for v in col.sample if v and v.strip()]
    hint = rules.name_type(col.column_name)
    negative = rules.has_negative_keyword(col.column_name)
    is_text = col.data_type in ("text", "character varying")

    if not sample:
        return _result(col, None, 0.0, "colonne vide")

    # Cas 1 : texte libre → on cherche des données personnelles À L'INTÉRIEUR du texte
    if is_text and col.avg_length >= rules.FREE_TEXT_MIN_LENGTH:
        found = [text_entities(v) for v in sample]
        ratio = sum(1 for f in found if f) / len(sample)
        types = sorted({t.removeprefix("MA_") for f in found for t in f})
        score = 0.0 if ratio == 0 else min(1.0, 0.6 + ratio)
        return _result(col, "FREE_TEXT", score,
                       f"texte libre : {ratio:.0%} des valeurs contiennent {', '.join(types) or 'rien'}")

    # Cas 2 : valeurs structurées → part des valeurs qui respectent chaque format
    evidence = {t: sum(1 for v in sample if rx.fullmatch(v)) / len(sample)
                for t, rx in rules.VALUE_REGEX.items()}
    best_type, best = max(evidence.items(), key=lambda kv: kv[1])
    source = f"regex {best_type} : {best:.0%} des valeurs"

    # Pas de format reconnu sur une colonne texte → on essaie le NER (noms de personnes)
    if is_text and best < 0.5:
        ner_ratio = sum(1 for v in sample if is_person_name(v)) / len(sample)
        if ner_ratio > best:
            best_type, best = "PERSON", ner_ratio
            source = f"NER PERSON : {ner_ratio:.0%} des valeurs"

    # Règle contextuelle : une colonne de type date nommée "naissance" est une date de naissance
    if col.data_type == "date" and hint == "DATE_OF_BIRTH":
        best_type, best, source = "DATE_OF_BIRTH", 1.0, "type date + nom de colonne"

    # Aucun indice dans les valeurs, mais le nom suggère un type → on le signale quand même
    if best < 0.3 and hint:
        best_type, best, source = hint, 0.0, "aucun indice dans les valeurs"
    elif best < 0.3:
        return _result(col, None, 0.0, "aucun indice")

    score = W_VALUES * best
    reasons = [source]
    if hint == best_type:
        score += W_NAME
        reasons.append("nom de colonne confirme")
    elif hint is None and best > 0:
        reasons.append("nom de colonne ne dit rien")
    if negative:
        score -= MALUS_NEGATIVE
        reasons.append("nom évoque un code métier (malus)")
    return _result(col, best_type, score, " ; ".join(reasons))


def _result(col: ColumnProfile, pii_type, score: float, evidence: str) -> Detection:
    score = round(max(0.0, min(1.0, score)), 2)
    if score >= rules.THRESHOLD_PII:
        decision = "PII"
    elif score >= rules.THRESHOLD_REVIEW:
        decision = "À vérifier"
    else:
        decision, pii_type = "Non sensible", None
    category, sensitivity = rules.CLASSIFICATION.get(pii_type, (None, "Interne"))
    return Detection(col.table_name, col.column_name, pii_type, category,
                     sensitivity, score, decision, evidence)


def detect_all(profiles: list[ColumnProfile]) -> list[Detection]:
    return [detect(p) for p in profiles]
