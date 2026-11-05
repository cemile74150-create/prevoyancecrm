# Demandes d'offres — rubrique Traitement

Notice établie à partir du code (`demandes_offres_routes.py`, `demandes_offres_3p.py`, `email_service.py`, `DemandeOffreFiche.js`). Le statut stocké n'a pas été remplacé.

## Comportement constaté dans le code (avant et encore en vigueur)

| Action | Qui | Effet en base | E-mail | Ce que voit l'agent |
| --- | --- | --- | --- | --- |
| Transmettre une offre (bouton historiquement « Offre reçue ») | Gestionnaire `demandes_offres.process` | Crée une offre compagnie, documents catégorie « Offre compagnie », statut **Offre reçue** | Oui, conseiller créateur (`offre_recue`) | Offre et message dans la fiche |
| Offres complètes | Gestionnaire, tant que le statut n'est pas déjà celui-là, hors dossiers terminés ou signés | `offres_completes_at/by`, message conseiller, statut **Offres complètes** | Oui, conseiller (`offres_completes`) | Bandeau « Message du gestionnaire » |
| Ajouter un document | Agent si brouillon / incomplète / attente d'infos ; sinon gestionnaire | Document dans la collection documents + ligne d'historique | Non | Pièce dans la liste |
| Note interne | Gestionnaire | `notes_internes` | Non | Masquée (historique interne filtré) |
| Note externe | Gestionnaire | `notes_externes`, complément optionnel « attendre une réponse » | Selon le flux de note déjà en place | Fil de discussion, réponse avec ou sans pièce |
| Erreurs | Gestionnaire | `erreurs_incomplete` / checklist, peut passer la compagnie en incomplète | Notification d'offre incomplète si cette action est lancée | Commentaire et champs signalés |
| Non soumis à la compagnie | Gestionnaire, case manuelle | `soumis_compagnie` booléen daté. Ne se coche pas à la signature | Non | Libellé sur la fiche |
| Demande annulée | Selon droits d'édition / process | Statut annulé, données conservées, restauration possible en brouillon | Selon le flux d'annulation existant | Demande hors cours, restaurable |

« Offres complètes » n'est pas un doublon de « Offre reçue » : la première dépose un document et passe à **Offre reçue** ; la seconde clôt la collecte et passe à **Offres complètes**, avec un e-mail distinct. Elle est conservée.

La signature (**Offre signée** / **Offre refusée**) reste le endpoint existant, avec document signé. Le nouveau suivi ne peut pas marquer « signée » tout seul.

## Changements apportés

- Libellé du bouton de dépôt : **Transmettre une offre**. Le statut technique reste `Offre reçue`.
- Encart statistiques agent sur la fiche : compteurs Demandes et Offres signées identiques au tableau de Gestion réponses offres. Le taux de signature est le même que `compute_stats` : signées / dossiers transmis au client (envoyée au client, en conclusion, signée ou refusée).
- Urgence : case + motif obligatoire à l'envoi. Un administrateur règle le quota dans Gestion réponses offres (activation, maximum, période mensuelle ou annuelle, usage par agent, exception +1). Quota désactivé par défaut.
- Liste : agent en évidence, RDV, badge Urgent, tris et filtres côté serveur sur le lot chargé.
- Suivi : les sept étapes restent affichées pour l'agent et le gestionnaire. La relance est un événement et laisse « En attente de la compagnie » en place. L'historique de la fiche montre la date, l'heure et l'auteur.
- Documents : glisser-déposer, collage d'image, catégories Offre / CGA / Autre document, case retour obligatoire. L'agent dépose la version complétée, liée au document attendu. Le gestionnaire confirme ensuite la réception. Les anciennes catégories (pièce jointe, mandat) restent valides.
- E-mails : « Transmettre une offre » envoie « Offre reçue ». « Offres complètes » n'envoie un second e-mail que s'il contient une note du gestionnaire, ou si aucune offre n'avait encore été notifiée. Le statut et la notification dans LeoSoft restent enregistrés.

## Points encore ouverts
- « Offre envoyée au client » continue de passer par le bouton existant, qui change le statut et déclenche le flux déjà en place. Le journal de suivi ne duplique pas cet e-mail.
- Le tampon LS n'est pas implémenté. Voir `docs/tampon-ls-faisabilite.md`.
