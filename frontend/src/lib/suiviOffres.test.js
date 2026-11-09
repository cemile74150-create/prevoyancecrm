import fs from "fs";
import path from "path";
import {
  A_ATTRIBUER_COLUMNS,
  BOUTON_TRAITER_CLASS,
  DETAIL_COLUMNS,
  FILTRES_VIDES,
  NON_ATTRIBUE,
  REPARTITION_COLUMNS,
  STATS_MENSUELLES_SERIES,
  boutonTraiter,
  commercialLabel,
  filtrerDetail,
  filtresActifs,
  listerNonAttribuees,
  matchTag,
  statsMensuellesParams,
  statsMensuellesVides,
  tauxSignatureLabel,
  trierRepartition,
} from "./suiviOffres";
import { FILE_COLUMNS } from "./transmissionOffre";

const src = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");

const row = (id, extra = {}) => ({
  id,
  agent_label: "Camille Durand",
  form_type: "pilier3",
  compagnies: ["AXA"],
  statut_traitement: "en_cours",
  statut_commercial: "non_renseigne",
  pilotage_tags: ["soumises", "attribuees", "traitement:en_cours"],
  ...extra,
});

describe("colonnes", () => {
  it("statut traitement et statut commercial sont deux colonnes distinctes", () => {
    expect(FILE_COLUMNS[0]).toBe("Agent");
    expect(FILE_COLUMNS[1]).toBe("Client");
    const t = FILE_COLUMNS.indexOf("Statut traitement");
    expect(t).toBeGreaterThan(-1);
    expect(FILE_COLUMNS[t + 1]).toBe("Statut commercial");
    expect(FILE_COLUMNS).not.toContain("Statut");
  });

  it("tableau détaillé dans l'ordre du cahier des charges", () => {
    expect(DETAIL_COLUMNS).toEqual([
      "Réf. OFF", "Agent demandeur", "Gestionnaire attribué", "Date de soumission", "Date RDV client",
      "Type d'offre", "Compagnie(s)", "Statut traitement", "Statut commercial", "Jours",
      "Priorité / Urgence", "Dernière action", "Actions",
    ]);
    expect(REPARTITION_COLUMNS.map((c) => c.label)).toEqual([
      "Gestionnaire", "Attribués", "En cours", "En attente compagnie", "Transmis à l'agent",
      "Signés", "Non signés", "En retard",
    ]);
    expect(A_ATTRIBUER_COLUMNS).toEqual([
      "Réf. OFF", "Agent demandeur", "Date de soumission", "Date RDV client", "Type d'offre",
      "Compagnie(s)", "Statut traitement", "Jours", "Priorité / Urgence", "Actions",
    ]);
  });
});

describe("bouton Traiter dynamique", () => {
  it("reprend le libellé et la couleur fournis par l'API", () => {
    expect(boutonTraiter({ bouton_traiter: { label: "Relancée", couleur: "violet" } }))
      .toEqual({ label: "Relancée", className: BOUTON_TRAITER_CLASS.violet });
    expect(boutonTraiter({ bouton_traiter: { label: "Traiter", couleur: "bleu" } }).className).toMatch(/002FA7/);
    expect(boutonTraiter({ bouton_traiter: { label: "Attente compagnie", couleur: "jaune" } }).className).toMatch(/yellow/);
    expect(boutonTraiter({}).label).toBe("Voir");
  });
});

describe("filtres cumulables", () => {
  const rows = [
    row("a"),
    row("b", { gestionnaire_id: "g1", statut_traitement: "attente_compagnie", pilotage_tags: ["soumises", "traitement:relance"] }),
    row("c", { gestionnaire_id: "g1", statut_commercial: "signee", pilotage_tags: ["soumises", "commercial:signee"], urgente: true }),
    row("d", { pilotage_tags: [] }),
  ];

  it("combine gestionnaire, statut commercial et priorité", () => {
    expect(filtrerDetail(rows).map((r) => r.id)).toEqual(["a", "b", "c"]);
    expect(filtrerDetail(rows, { gestionnaire: NON_ATTRIBUE }).map((r) => r.id)).toEqual(["a"]);
    expect(filtrerDetail(rows, { gestionnaire: "g1", commercial: "signee" }).map((r) => r.id)).toEqual(["c"]);
    expect(filtrerDetail(rows, { gestionnaire: "g1", priorite: "urgence_agent" }).map((r) => r.id)).toEqual(["c"]);
    expect(filtrerDetail(rows, { tag: "attente_compagnie_ou_relance" }).map((r) => r.id)).toEqual(["b"]);
    expect(filtresActifs({ gestionnaire: "g1" })).toBe(true);
    expect(filtresActifs({})).toBe(false);
  });

  it("En attente compagnie inclut les dossiers relancés", () => {
    expect(matchTag(rows[1], "attente_compagnie_ou_relance")).toBe(true);
  });
});

describe("répartition des gestionnaires", () => {
  it("tri par colonne, la ligne Non attribué reste en dernier", () => {
    const lignes = [
      { id: NON_ATTRIBUE, nom: "Non attribué", attribues: 9 },
      { id: "g1", nom: "Lea", attribues: 2 },
      { id: "g2", nom: "Marc", attribues: 5 },
    ];
    expect(trierRepartition(lignes, "attribues", "desc").map((l) => l.id)).toEqual(["g2", "g1", NON_ATTRIBUE]);
    expect(trierRepartition(lignes, "nom", "asc").map((l) => l.id)).toEqual(["g1", "g2", NON_ATTRIBUE]);
  });
});

describe("file d'attribution", () => {
  it("liste uniquement les non attribuées, plus anciennes en premier", () => {
    const rows = [
      row("new", { date_envoi: "2026-03-10", numero: "OFF-2", pilotage_tags: ["soumises", "non_attribuees"] }),
      row("old", { date_envoi: "2026-01-05", numero: "OFF-1", pilotage_tags: ["soumises", "non_attribuees"] }),
      row("taken", { gestionnaire_id: "g1", date_envoi: "2025-12-01", pilotage_tags: ["soumises", "attribuees"] }),
      row("draft", { date_envoi: "2025-01-01", pilotage_tags: [] }),
    ];
    expect(listerNonAttribuees(rows).map((r) => r.id)).toEqual(["old", "new"]);
  });
});

describe("libellés", () => {
  it("ancien dossier sans décision : Statut non renseigné", () => {
    expect(commercialLabel({})).toBe("Statut non renseigné");
    expect(tauxSignatureLabel(null)).toBe("—");
    expect(tauxSignatureLabel(66.7)).toBe("66,7 %");
  });

  it("Suivi de mon offre regroupe les boutons existants de l'agent créateur", () => {
    const fiche = src("pages/DemandeOffreFiche.js");
    const start = fiche.indexOf('data-testid="suivi-mon-offre"');
    expect(start).toBeGreaterThan(-1);
    const block = fiche.slice(start, fiche.indexOf("</div>\n    )}", start));
    expect(block).toMatch(/offre-envoyee-client-btn/);
    expect(block).toMatch(/offre-signee-btn/);
    expect(block).toMatch(/offre-non-signee-panel-btn/);
    expect(fiche).toMatch(/showConseillerFollowup && demande\.statut !== "Brouillon"/);
    expect(fiche).toMatch(/viewerIsCreatingAgent\(demande, user/);
  });

  it("le tableau de bord global utilise un seul calcul d'indicateurs", () => {
    const pilotage = src("components/SuiviOffresPilotage.js");
    expect(pilotage).toMatch(/\/demandes-offres\/pilotage/);
    expect(pilotage).not.toMatch(/statut === "Offre signée"/);
    const gestion = src("pages/GestionReponsesOffres.js");
    expect(gestion).toMatch(/perimetre: "personnel"/);
  });

  it("Suivi des offres : file d'attribution directe, sans tableau décision client", () => {
    const pilotage = src("components/SuiviOffresPilotage.js");
    expect(pilotage).toMatch(/dossiers-a-attribuer/);
    expect(pilotage).toMatch(/a-attribuer-btn-/);
    expect(pilotage).toMatch(/listerNonAttribuees/);
    expect(pilotage).toMatch(/\/demandes-offres\/\$\{row\.id\}\/attribuer/);
    expect(pilotage).not.toMatch(/data-testid="decision-a-renseigner"/);
    expect(pilotage).not.toMatch(/Décision client à renseigner/);
    expect(pilotage).toMatch(/Répartition et activité des gestionnaires/);
  });

  it("lignes des listes offres cliquables pour ouvrir la fiche, actions isolées", () => {
    const pilotage = src("components/SuiviOffresPilotage.js");
    const gestion = src("pages/GestionReponsesOffres.js");
    expect(gestion).toMatch(/data-testid=\{`file-row-\$\{r\.id\}`\}/);
    expect(gestion).toMatch(/onClick=\{\(\) => openFiche\(r\.id\)\}/);
    expect(gestion).toMatch(/role="button"/);
    expect(gestion).toMatch(/onClick=\{\(e\) => e\.stopPropagation\(\)\}/);
    expect(pilotage).toMatch(/data-testid=\{`a-attribuer-\$\{r\.id\}`\}/);
    expect(pilotage).toMatch(/data-testid=\{`detail-row-\$\{r\.id\}`\}/);
    expect(pilotage).toMatch(/onClick=\{\(\) => openFiche\(r\)\}/);
    expect(pilotage).toMatch(/role="button"/);
    expect(pilotage).toMatch(/onClick=\{\(e\) => e\.stopPropagation\(\)\}/);
    expect(pilotage).toMatch(/event\?\.stopPropagation\?\./);
  });

  it("Mes dossiers : indicateurs haut + file Demandes à traiter, sans grille KPI dense", () => {
    const gestion = src("pages/GestionReponsesOffres.js");
    expect(gestion).toMatch(/Mes indicateurs — avancement du traitement/);
    expect(gestion).toMatch(/Mes indicateurs — résultat commercial/);
    expect(gestion).toMatch(/file-demandes-a-traiter/);
    expect(gestion).toMatch(/Demandes à traiter/);
    expect(gestion).toMatch(/boutonTraiter\(r\)/);
    expect(gestion).toMatch(/file-attribuer-/);
    expect(gestion).not.toMatch(/GESTION_KPI_CARDS/);
    expect(gestion).not.toMatch(/mes-decision-a-renseigner/);
    expect(gestion).not.toMatch(/Décision client à renseigner/);
  });
});

describe("statistiques mensuelles des offres", () => {
  it("6 mois par défaut, 12 en option, rien d'autre", () => {
    expect(statsMensuellesParams()).toEqual({ mois: 6, periode: "all" });
    expect(statsMensuellesParams({ mois: 12 }).mois).toBe(12);
    expect(statsMensuellesParams({ mois: 7 }).mois).toBe(6);
  });

  it("reprend période, agent, gestionnaire, type et compagnie du pilotage", () => {
    const params = statsMensuellesParams({
      mois: 12,
      periode: "custom",
      dateDe: "2026-09-01",
      dateA: "2026-10-31",
      conseiller: "Camille Durand",
      filtres: { ...FILTRES_VIDES, gestionnaire: NON_ATTRIBUE, type: "pilier3", compagnie: "AXA", tag: "soumises" },
    });
    expect(params).toEqual({
      mois: 12,
      periode: "custom",
      date_de: "2026-09-01",
      date_a: "2026-10-31",
      conseiller: "Camille Durand",
      gestionnaire: NON_ATTRIBUE,
      form_type: "pilier3",
      compagnie: "AXA",
    });
    expect(statsMensuellesParams({ periode: "month", dateDe: "2026-09-01", conseiller: "all" })).toEqual({ mois: 6, periode: "month" });
    expect(statsMensuellesParams({ perimetre: "personnel" }).perimetre).toBe("personnel");
  });

  it("état vide tant qu'aucune série n'a de valeur", () => {
    expect(statsMensuellesVides(null)).toBe(true);
    expect(statsMensuellesVides({ mois: [{ mois: "2026-11", recues: 0, signees: 0, non_signees: 0 }] })).toBe(true);
    expect(statsMensuellesVides({ mois: [{ mois: "2026-11", recues: 0, signees: 0, non_signees: 1 }] })).toBe(false);
  });

  it("trois séries de couleurs distinctes", () => {
    expect(STATS_MENSUELLES_SERIES.map((s) => s.label)).toEqual(["Offres reçues", "Offres signées", "Offres non signées"]);
    expect(new Set(STATS_MENSUELLES_SERIES.map((s) => s.color)).size).toBe(3);
  });

  it("graphique sous les indicateurs du pilotage, même composant que les stats Prévoyance", () => {
    const pilotage = src("components/SuiviOffresPilotage.js");
    const resultat = pilotage.indexOf("Résultat commercial</h2>");
    const graphique = pilotage.indexOf("<OffresStatsMensuelles");
    const pipeline = pilotage.indexOf("Pipeline des offres</h2>");
    expect(resultat).toBeGreaterThan(-1);
    expect(graphique).toBeGreaterThan(resultat);
    expect(pipeline).toBeGreaterThan(graphique);
    expect(src("components/OffresStatsMensuelles.js")).toMatch(/<MonthlyBarChart/);
    expect(src("components/OffresStatsMensuelles.js")).toMatch(/\/demandes-offres\/pilotage\/mensuel/);
    expect(src("pages/Dashboard.js")).toMatch(/<MonthlyBarChart data=\{prev\.monthly\}/);
    expect(src("components/OffresDashboardPanel.js")).toMatch(/<OffresStatsMensuelles \/>/);
  });
});
