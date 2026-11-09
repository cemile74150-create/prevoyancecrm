import fs from "fs";
import path from "path";
import {
  BOUTON_TRAITER_CLASS,
  DETAIL_COLUMNS,
  NON_ATTRIBUE,
  REPARTITION_COLUMNS,
  boutonTraiter,
  commercialLabel,
  filtrerDetail,
  filtresActifs,
  matchTag,
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
});
