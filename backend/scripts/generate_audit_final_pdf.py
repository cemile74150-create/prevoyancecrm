"""
Génère le PDF d'audit final PrevoyanceCRM (28 août 2026).
Contenu basé uniquement sur des vérifications effectuées en production.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm, mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "Audit_final_PrevoyanceCRM_28-08-2026.pdf"

# --- Faits vérifiés (28 août 2026) ---
FACTS = {
    "audit_date": "28 août 2026",
    "prod_url": "https://prevoyance-frontend-production.up.railway.app",
    "mongo_volume_gb": "5 Go",
    "mongo_volume_before": "500 Mo",
    "mongo_fs_free_gib": "4,16",
    "mongo_fs_used_mib": "212,7",
    "mongo_data_mb": "~1,6",
    "mongo_docs_total": "2 077",
    "mongo_collections": "17",
    "mongo_indexes": "16/16",
    "active_s3_refs": "539",
    "unique_s3_paths": "537",
    "s3_missing": "0",
    "backup_date": "28 août 2026",
    "backup_files_ok": "851",
    "backup_remote": "prevoyancecrm-backups (Infomaniak)",
    "clients_count": "74",
    "documents_count": "620",
    "actions_count": "848",
}


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "AuditTitle",
            parent=base["Title"],
            fontName="Helvetica-Bold",
            fontSize=22,
            leading=28,
            textColor=colors.HexColor("#1a365d"),
            spaceAfter=14,
            alignment=TA_CENTER,
        ),
        "subtitle": ParagraphStyle(
            "AuditSubtitle",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#4a5568"),
            alignment=TA_CENTER,
            spaceAfter=20,
        ),
        "h1": ParagraphStyle(
            "AuditH1",
            parent=base["Heading1"],
            fontName="Helvetica-Bold",
            fontSize=15,
            leading=20,
            textColor=colors.HexColor("#1a365d"),
            spaceBefore=18,
            spaceAfter=10,
        ),
        "h2": ParagraphStyle(
            "AuditH2",
            parent=base["Heading2"],
            fontName="Helvetica-Bold",
            fontSize=12,
            leading=16,
            textColor=colors.HexColor("#2c5282"),
            spaceBefore=12,
            spaceAfter=6,
        ),
        "body": ParagraphStyle(
            "AuditBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=16,
            alignment=TA_JUSTIFY,
            spaceAfter=8,
        ),
        "bullet": ParagraphStyle(
            "AuditBullet",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=11,
            leading=15,
            leftIndent=14,
            bulletIndent=0,
            spaceAfter=5,
        ),
        "box_title": ParagraphStyle(
            "BoxTitle",
            parent=base["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=17,
            textColor=colors.white,
            alignment=TA_CENTER,
        ),
        "box_body": ParagraphStyle(
            "BoxBody",
            parent=base["Normal"],
            fontName="Helvetica",
            fontSize=10.5,
            leading=15,
            textColor=colors.HexColor("#1a202c"),
        ),
        "footer": ParagraphStyle(
            "Footer",
            parent=base["Normal"],
            fontName="Helvetica-Oblique",
            fontSize=9,
            textColor=colors.HexColor("#718096"),
            alignment=TA_CENTER,
        ),
    }


def _table(data, col_widths=None):
    t = Table(data, colWidths=col_widths, repeatRows=1)
    t.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2c5282")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 10),
                ("FONTNAME", (0, 1), (-1, -1), "Helvetica"),
                ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f7fafc")]),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#cbd5e0")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
            ]
        )
    )
    return t


def _status_box(st):
    title = Paragraph("État au 28 août 2026 : conforme / opérationnel", st["box_title"])
    rows = [
        ["Indicateur", "Résultat vérifié"],
        ["Application production", "En ligne"],
        ["Documents actifs sur S3", f"{FACTS['active_s3_refs']} références — {FACTS['s3_missing']} manquante"],
        ["Index MongoDB", FACTS["mongo_indexes"]],
        ["Volume MongoDB", f"{FACTS['mongo_volume_gb']} ({FACTS['mongo_fs_free_gib']} GiB libres)"],
        ["Sauvegarde Infomaniak", f"{FACTS['backup_date']} — {FACTS['backup_files_ok']} fichiers OK"],
        ["Dépendance Emergent (runtime)", "Aucune"],
    ]
    inner = _table(rows, col_widths=[6.5 * cm, 9.5 * cm])
    box_data = [[title], [inner]]
    box = Table(box_data, colWidths=[16.5 * cm])
    box.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#276749")),
                ("BOX", (0, 0), (-1, -1), 1.2, colors.HexColor("#276749")),
                ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ("RIGHTPADDING", (0, 0), (-1, -1), 10),
                ("TOPPADDING", (0, 0), (0, 0), 12),
                ("BOTTOMPADDING", (0, 0), (0, 0), 12),
                ("TOPPADDING", (0, 1), (-1, -1), 8),
                ("BOTTOMPADDING", (0, 1), (-1, -1), 10),
            ]
        )
    )
    return box


def _on_page(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#718096"))
    canvas.drawString(2 * cm, 1.2 * cm, "Audit final — PrevoyanceCRM — Document de référence")
    canvas.drawRightString(A4[0] - 2 * cm, 1.2 * cm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def build_pdf():
    st = _styles()
    doc = SimpleDocTemplate(
        str(OUTPUT),
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2.2 * cm,
        title="Audit final PrevoyanceCRM",
        author="Audit technique CRM",
    )
    story = []

    # --- Page 1 : couverture + résumé exécutif ---
    story.append(Paragraph("Audit final", st["title"]))
    story.append(Paragraph("PrevoyanceCRM", st["title"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(f"Date de l'audit : {FACTS['audit_date']}", st["subtitle"]))
    story.append(Spacer(1, 12))
    story.append(_status_box(st))
    story.append(Spacer(1, 18))
    story.append(Paragraph("Résumé exécutif", st["h1"]))
    story.append(
        Paragraph(
            "Ce document résume l'état du CRM PrevoyanceCRM après migration des documents "
            "vers le stockage Infomaniak, nettoyage de la dépendance à la plateforme Emergent, "
            "correction de l'espace disque MongoDB et vérifications de cohérence réalisées "
            "le 28 août 2026. Il est destiné à être conservé comme preuve et présenté "
            "à la direction, à un client ou à un prestataire.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "Les chiffres et affirmations ci-dessous proviennent de contrôles effectués "
            "en lecture seule ou de tests validés en production. Aucune donnée métier "
            "n'a été supprimée dans le cadre de cet audit.",
            st["body"],
        )
    )

    # --- Section 1 ---
    story.append(PageBreak())
    story.append(Paragraph("1. Présentation du CRM et architecture actuelle", st["h1"]))
    story.append(
        Paragraph(
            "PrevoyanceCRM est l'application de gestion de la relation client et du suivi "
            "des dossiers de prévoyance. Elle est utilisée en production par l'agence.",
            st["body"],
        )
    )
    story.append(_table(
        [
            ["Composant", "Rôle", "Hébergement"],
            ["Interface web", "Consultation et saisie CRM", "Railway (service prevoyance-frontend)"],
            ["Serveur applicatif", "API, logique métier, génération PDF", "Railway (même service)"],
            ["Base de données", "Données clients, dossiers, actions", "Railway (MongoDB dédié)"],
            ["Stockage fichiers", "PDF et documents clients", "Infomaniak Object Storage (S3)"],
            ["Sauvegardes", "Copies chiffrées hors Railway", "Infomaniak (bucket dédié)"],
        ],
        col_widths=[3.8 * cm, 5.5 * cm, 7.2 * cm],
    ))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            f"URL de production vérifiée : {FACTS['prod_url']}",
            st["body"],
        )
    )

    # --- Section 2 ---
    story.append(Paragraph("2. Migration Emergent vers Infomaniak S3", st["h1"]))
    story.append(
        Paragraph(
            "Historiquement, une partie des documents était hébergée via la plateforme Emergent. "
            "Une migration planifiée a transféré les références actives vers le stockage S3 Infomaniak. "
            "Les chemins de stockage dans MongoDB ont été mis à jour pour pointer vers S3.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "Après migration, un contrôle automatisé du 28 août 2026 a confirmé que toutes "
            f"les références actives ({FACTS['active_s3_refs']} entrées, {FACTS['unique_s3_paths']} fichiers "
            f"uniques) pointent vers S3 et sont lisibles. Aucune référence active manquante "
            f"({FACTS['s3_missing']}) n'a été détectée.",
            st["body"],
        )
    )

    # --- Section 3 ---
    story.append(Paragraph("3. Emergent n'est plus nécessaire au fonctionnement", st["h1"]))
    story.append(
        Paragraph(
            "Le code applicatif en production a été vérifié : le serveur initialise désormais "
            "uniquement le stockage S3 (message de démarrage « Storage initialized backend=s3 »). "
            "Aucune clé API Emergent ni URL de stockage Emergent n'est utilisée au runtime.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "En pratique, le CRM peut fonctionner sans compte Emergent actif. "
            "Des archives techniques de migration peuvent subsister dans le dépôt de code "
            "à titre documentaire ; elles ne sont pas exécutées en production.",
            st["body"],
        )
    )

    # --- Section 4 ---
    story.append(Paragraph("4. Stockage actuel des documents", st["h1"]))
    story.append(
        Paragraph(
            "Les documents clients (PDF générés, PDF uploadés, formulaires, pièces Suivi 3P) "
            "sont stockés sur Infomaniak Object Storage, compatible API S3. "
            "MongoDB ne contient que les métadonnées et le chemin de chaque fichier — "
            "pas les binaires eux-mêmes.",
            st["body"],
        )
    )
    story.append(
        KeepTogether(
            [
                _table(
                    [
                        ["Contrôle (28/08/2026)", "Résultat"],
                        ["Références actives analysées", FACTS["active_s3_refs"]],
                        ["Chemins S3 uniques testés", FACTS["unique_s3_paths"]],
                        ["Fichiers manquants ou illisibles", FACTS["s3_missing"]],
                        ["Références hors S3 (actives)", FACTS["s3_missing"]],
                    ],
                    col_widths=[8 * cm, 8.5 * cm],
                ),
                Spacer(1, 12),
            ]
        )
    )

    # --- Section 5 & 6 ---
    story.append(Paragraph("5. État de MongoDB après migration", st["h1"]))
    story.append(
        Paragraph(
            "La base MongoDB contient l'ensemble des données métier du CRM. "
            f"Au 28 août 2026, {FACTS['mongo_docs_total']} documents répartis sur "
            f"{FACTS['mongo_collections']} collections ont été comptés, sans modification "
            "ni suppression dans le cadre des opérations de cet audit.",
            st["body"],
        )
    )
    story.append(_table(
        [
            ["Indicateur", "Valeur vérifiée"],
            ["Volume de données logiques", f"{FACTS['mongo_data_mb']} Mo"],
            ["Clients", FACTS["clients_count"]],
            ["Documents (métadonnées)", FACTS["documents_count"]],
            ["Actions", FACTS["actions_count"]],
        ],
        col_widths=[8 * cm, 8.5 * cm],
    ))
    story.append(Spacer(1, 10))
    story.append(Paragraph("6. Volume MongoDB augmenté", st["h1"]))
    story.append(
        Paragraph(
            f"Le volume disque MongoDB est passé de {FACTS['mongo_volume_before']} à "
            f"{FACTS['mongo_volume_gb']}, afin de disposer de suffisamment d'espace "
            "pour la création des index et la croissance future. "
            "MongoDB voit désormais environ 4,36 GiB de capacité totale et "
            f"{FACTS['mongo_fs_free_gib']} GiB d'espace libre.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "L'espace utilisé sur disque (~213 MiB) inclut un écart connu lié au moteur "
            "de stockage WiredTiger (bloat). Les données métier réelles restent très faibles "
            f"({FACTS['mongo_data_mb']} Mo). Aucune opération de compact ou de purge "
            "n'a été réalisée.",
            st["body"],
        )
    )

    # --- Section 7 ---
    story.append(Paragraph("7. Index MongoDB — 16/16 présents", st["h1"]))
    story.append(
        Paragraph(
            "Des index de performance étaient définis dans le code mais n'avaient pas pu "
            "être créés faute d'espace disque. Après augmentation du volume et redémarrage "
            "de l'application, les 16 index prévus ont été créés automatiquement au démarrage. "
            "Un contrôle en lecture seule du 28 août 2026 confirme leur présence. "
            "Aucune erreur d'espace disque n'a été observée lors de ce redémarrage.",
            st["body"],
        )
    )
    story.append(
        KeepTogether(
            [
                _table(
                    [
                        ["Collection", "Nombre d'index métier"],
                        ["clients", "4"],
                        ["documents", "2"],
                        ["notes, demandes, actions, rendez-vous, tâches", "1 chacune"],
                        ["suivi_3p_clients, suivi_3p_documents", "1 chacune"],
                        ["users", "1"],
                        ["user_sessions", "2"],
                        ["Total vérifié", "16/16"],
                    ],
                    col_widths=[8 * cm, 8.5 * cm],
                ),
                Spacer(1, 12),
            ]
        )
    )

    # --- Section 8 ---
    story.append(Paragraph("8. Vérification des documents actifs", st["h1"]))
    story.append(
        Paragraph(
            f"Le script de vérification « verify_active_refs_full » exécuté le 28 août 2026 "
            f"a parcouru {FACTS['active_s3_refs']} références actives dans MongoDB, "
            f"testé {FACTS['unique_s3_paths']} fichiers S3 uniques, et constaté "
            f"{FACTS['s3_missing']} fichier manquant ou illisible.",
            st["body"],
        )
    )

    # --- Section 9 ---
    story.append(Paragraph("9. Tests fonctionnels validés", st["h1"]))
    story.append(
        Paragraph(
            "Les scénarios suivants ont été validés en environnement de production "
            "dans le cadre de la migration et des contrôles post-déploiement :",
            st["body"],
        )
    )
    for item in [
        "Connexion et authentification",
        "Consultation des fiches clients",
        "Téléchargement d'un document PDF",
        "Upload d'un document PDF",
        "Module Suivi 3P",
    ]:
        story.append(Paragraph(f"• {item}", st["bullet"]))
    story.append(
        Paragraph(
            "Ces validations ont été effectuées manuellement en production. "
            "Une suite de tests automatisés existe côté backend ; son exécution locale "
            "peut dépendre de la configuration de l'environnement de test.",
            st["body"],
        )
    )

    # --- Section 10 ---
    story.append(PageBreak())
    story.append(Paragraph("10. Sauvegarde Infomaniak — réalisée et restaurable", st["h1"]))
    story.append(
        Paragraph(
            f"Une sauvegarde professionnelle complète a été réalisée le {FACTS['backup_date']}. "
            "Elle inclut l'export MongoDB (17 collections) et le téléchargement des fichiers actifs.",
            st["body"],
        )
    )
    story.append(_table(
        [
            ["Élément", "Résultat vérifié"],
            ["Fichiers actifs sauvegardés", f"{FACTS['backup_files_ok']} OK, 0 échec"],
            ["Intégrité (manifest SHA256)", "OK"],
            ["Chiffrement", "AES-256-GCM (.crmbak)"],
            ["Copie distante", FACTS["backup_remote"]],
            ["Taille distante = taille locale", "Vérifiée"],
            ["Test déchiffrement + extraction", "OK"],
        ],
        col_widths=[7.5 * cm, 9 * cm],
    ))
    story.append(
        Paragraph(
            "Nom de l'archive : prevoyancecrm_backup_20260828_125733.tar.gz.crmbak",
            st["body"],
        )
    )

    # --- Section 11 ---
    story.append(Paragraph("11. Sécurité et sauvegardes — où sont les données ?", st["h1"]))
    story.append(
        Paragraph(
            "Voici, de manière simplifiée, la répartition et la protection des données :",
            st["body"],
        )
    )
    story.append(_table(
        [
            ["Type de donnée", "Où elle se trouve", "Sauvegarde"],
            ["Données CRM (clients, actions…)", "MongoDB sur Railway", "Export JSONL chiffré sur Infomaniak"],
            ["Documents PDF / fichiers", "Bucket S3 Infomaniak (prod)", "Inclus dans la sauvegarde professionnelle"],
            ["Copies de secours", "Bucket Infomaniak dédié (prevoyancecrm-backups)", "Rétention : 7 dernières archives"],
        ],
        col_widths=[4.5 * cm, 5.5 * cm, 6.5 * cm],
    ))
    story.append(Spacer(1, 8))
    story.append(
        Paragraph(
            "Les sauvegardes sont chiffrées et stockées indépendamment de Railway. "
            "La phrase secrète de chiffrement n'est pas stockée dans ce document "
            "et doit être conservée séparément par le responsable du CRM.",
            st["body"],
        )
    )

    # --- Points importants ---
    story.append(Paragraph("Points importants à retenir", st["h1"]))
    points = [
        "Le CRM fonctionne en production sans dépendance opérationnelle à Emergent.",
        f"Toutes les références actives vérifiées ({FACTS['active_s3_refs']}) pointent vers S3 Infomaniak et sont lisibles.",
        f"MongoDB dispose de {FACTS['mongo_volume_gb']} d'espace disque ; les 16 index métier sont en place.",
        f"Aucune donnée métier n'a été supprimée lors des opérations du 28 août 2026.",
        f"Une sauvegarde complète du {FACTS['backup_date']} est disponible sur Infomaniak, avec restaurabilité vérifiée.",
        "Les documents clients ne sont pas stockés dans MongoDB, mais sur le stockage objet Infomaniak.",
        "Ce document reflète l'état vérifié au 28 août 2026 et peut servir de référence en cas de contrôle.",
    ]
    for p in points:
        story.append(Paragraph(f"• {p}", st["bullet"]))

    # --- Conclusion ---
    story.append(Spacer(1, 16))
    story.append(Paragraph("Conclusion", st["h1"]))
    story.append(
        Paragraph(
            "Au 28 août 2026, PrevoyanceCRM est opérationnel en production. "
            "La migration des documents vers Infomaniak S3 est terminée et vérifiée. "
            "La contrainte d'espace disque MongoDB a été levée par le passage à un volume de 5 Go, "
            "permettant la mise en place des index nécessaires aux performances. "
            "Une sauvegarde récente, chiffrée et restaurable, est disponible hors Railway.",
            st["body"],
        )
    )
    story.append(
        Paragraph(
            "Le CRM ne dépend plus d'Emergent pour son fonctionnement quotidien. "
            "Les contrôles réalisés couvrent la cohérence des documents actifs, "
            "l'état de la base de données et la disponibilité des sauvegardes — "
            "sans prétendre à une garantie absolue future, qui nécessiterait une surveillance continue.",
            st["body"],
        )
    )
    story.append(Spacer(1, 24))
    story.append(
        Paragraph(
            f"Document généré le {date.today().strftime('%d/%m/%Y')} — Audit final PrevoyanceCRM",
            st["footer"],
        )
    )

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return OUTPUT


if __name__ == "__main__":
    path = build_pdf()
    size = path.stat().st_size
    print(f"OK: {path}")
    print(f"size_bytes={size}")
