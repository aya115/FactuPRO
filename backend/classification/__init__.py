# -*- coding: utf-8 -*-
"""
Module de classification supervisée des charges de facture.
Utilise TF-IDF + RandomForest pour classifier les descriptions d'articles.
"""

from .predictor import ExpenseClassifier

__all__ = ["ExpenseClassifier"]
