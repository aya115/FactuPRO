---
title Cas d'utilisation - Plateforme Factures IA
---
usecaseDiagram
left to right direction

actor Comptable as C
actor Superviseur as S
actor Admin as A

rectangle "Application Factures IA" {

  rectangle "Espace Comptable" {
    (Uploader une facture) as UC_Upload_C
    (Lancer OCR + extraction) as UC_OCR_C
    (Consulter mes factures) as UC_MyInv
    (Voir détail d'une facture) as UC_Detail_C
    (Utiliser l'assistant IA factures) as UC_IA_C
  }

  rectangle "Espace Superviseur" {
    (Consulter toutes les factures) as UC_AllInv_S
    (Voir détail d'une facture) as UC_Detail_S
    (Utiliser l'assistant IA factures) as UC_IA_S
    (Voir métriques globales) as UC_Metrics_S
  }

  rectangle "Espace Admin" {
    (Consulter toutes les factures) as UC_AllInv_A
    (Voir détail d'une facture) as UC_Detail_A
    (Voir métriques globales) as UC_Metrics_A
    (Gérer les utilisateurs) as UC_Users
  }

  rectangle "Authentification" {
    (Se connecter / S'authentifier) as UC_Login
    (Consulter mon profil) as UC_Profile
  }
}

%% Comptable
C --> UC_Upload_C
C --> UC_OCR_C
C --> UC_MyInv
C --> UC_Detail_C
C --> UC_IA_C
C --> UC_Profile

%% Superviseur
S --> UC_AllInv_S
S --> UC_Detail_S
S --> UC_IA_S
S --> UC_Metrics_S
S --> UC_Profile

%% Admin
A --> UC_AllInv_A
A --> UC_Detail_A
A --> UC_Metrics_A
A --> UC_Users
A --> UC_Profile

%% Tous les cas d'utilisation incluent l'authentification
UC_Upload_C ..> UC_Login : <<include>>
UC_OCR_C ..> UC_Login : <<include>>
UC_MyInv ..> UC_Login : <<include>>
UC_Detail_C ..> UC_Login : <<include>>
UC_IA_C ..> UC_Login : <<include>>

UC_AllInv_S ..> UC_Login : <<include>>
UC_Detail_S ..> UC_Login : <<include>>
UC_IA_S ..> UC_Login : <<include>>
UC_Metrics_S ..> UC_Login : <<include>>

UC_AllInv_A ..> UC_Login : <<include>>
UC_Detail_A ..> UC_Login : <<include>>
UC_Metrics_A ..> UC_Login : <<include>>
UC_Users ..> UC_Login : <<include>>
