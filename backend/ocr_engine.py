import numpy as np
from rapidfuzz import fuzz

def similarity_match(a, b, threshold=95):
    if a is None:
        a = ""
    if b is None:
        b = ""

    a = str(a).strip().lower()
    b = str(b).strip().lower()

    if a == b:
        return True

    import difflib
    score = difflib.SequenceMatcher(None, a, b).ratio() * 100

    return score >= threshold


def numeric_match(a, b, tolerance=1e-2):

    def normalize(v):
        try:
            return float(v)
        except:
            return None

    n1 = normalize(a)
    n2 = normalize(b)
    if not str(a).strip() and not str(b).strip():
        return True
    if n1 is not None and n2 is not None:
        return abs(n1 - n2) <= tolerance

    return similarity_match(a, b)