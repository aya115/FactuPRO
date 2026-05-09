# test_model.py
from google.genai import Client

# Clé API
client = Client(api_key="AIzaSyAiUwEhpEDnmd7pZEaNfFKOTHPI-JSnvjk")

# Liste des modèles
models = client.models.list()

for model in models:
    print("Nom du modèle:", model.name)
    # Vérifie si description existe
    if hasattr(model, "description"):
        print("Description:", model.description)
    # Si paramètres disponibles
    if hasattr(model, "parameters"):
        print("Paramètres:", model.parameters)
    print("-" * 50)