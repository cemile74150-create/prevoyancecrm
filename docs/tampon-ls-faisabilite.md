# Tampon « LS » sur les PDF d'offre — faisabilité

Analyse seulement. Aucun PDF en production n'est modifié.

## Constat technique

Les offres déposées passent par `store_doc` (`demandes_offres_routes.py`) : octets d'origine, clé de stockage, nom de fichier. Le générateur PyMuPDF existe déjà pour d'autres PDF (formulaires AVS), donc un overlay « LS » en haut à droite de la page 1 est techniquement faisable au moment de l'upload, avant écriture.

## Risques

- Un PDF déjà signé numériquement devient invalide dès qu'on réécrit une page. Il ne faut tamponner que les PDF déposés par le service des Offres, pas les retours signés.
- Certains PDF sont des images ou des portfolios : l'overlay peut échouer. Il faut alors garder le fichier original et signaler l'échec, sans remplacer le document.
- Le tampon ne doit pas couvrir un logo ou un montant. L'emplacement « coin haut droit » reste un choix visuel à valider sur de vrais spécimens.
- Application rétroactive exclue : seulement les dépôts après activation d'un réglage, désactivable.

## Recommandation

Paramètre admin `tampon_ls` désactivé par défaut. À l'upload d'une offre compagnie PDF, produire une copie tamponnée et conserver l'original si le traitement échoue. Ne pas toucher aux documents déjà stockés ni aux pièces retournées par l'agent.
