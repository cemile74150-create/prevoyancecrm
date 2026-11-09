import fs from "fs";
import path from "path";
import {
  FILE_COLUMNS,
  PARCOURS_FIELDS,
  PARCOURS_REPONSES,
  PARCOURS_TRAITEMENT,
  SIGNALER_ERREUR_CLASS,
  VARIANTE_PIECES,
  documentsParVariante,
  emptyVariante,
  messageTransmission,
  parseNbVariantes,
  resizeVariantes,
  sortFileATraiter,
  traitementFormData,
  traitementManquantes,
  urgentesAgentEnTete,
  urgenceDelaiLabel,
  urgenceRefus,
  variantesFormData,
  variantesManquantes,
} from "./transmissionOffre";
import { avancementCode, avancementLabel, formatVariantesSummary } from "./demandesOffres";

const src = (rel) => fs.readFileSync(path.join(__dirname, "..", rel), "utf8");
const file = (name) => new File(["x"], name, { type: "application/pdf" });

describe("libellé Offres sollicitées", () => {
  it("remplace Variantes sollicitées sur les écrans visibles", () => {
    ["pages/DemandesOffres.js", "components/OffresDashboardPanel.js", "pages/DemandeOffreFiche.js", "pages/GestionReponsesOffres.js"]
      .forEach((rel) => expect(src(rel)).not.toMatch(/Variantes sollicitées/));
    expect(src("components/OffresDashboardPanel.js")).toMatch(/label: "Offres sollicitées"/);
    expect(src("pages/DemandesOffres.js")).toMatch(/"nb_variantes_sollicitees", "Offres sollicitées"/);
    expect(formatVariantesSummary({ nb_variantes_sollicitees: 2, compagnies: ["AXA", "Zurich"] }))
      .toBe("2 offres sollicitées · AXA, Zurich");
  });
});

describe("variantes", () => {
  it("vaut 1 par défaut et n'accepte qu'un entier positif", () => {
    expect(parseNbVariantes("")).toBe(1);
    expect(parseNbVariantes(undefined)).toBe(1);
    expect(parseNbVariantes("3")).toBe(3);
    ["0", "-2", "1.5", "abc", "21"].forEach((v) => expect(parseNbVariantes(v)).toBeNull());
  });

  it("trois variantes donnent trois blocs Offre, CGA, Autre document", () => {
    const { variantes } = resizeVariantes([emptyVariante()], 3);
    expect(variantes).toHaveLength(3);
    variantes.forEach((v) => expect(Object.keys(v)).toEqual(["offre", "cga", "autre"]));
    expect(VARIANTE_PIECES.map((p) => [p.label, p.required])).toEqual([
      ["Offre", true], ["CGA", false], ["Autre document", false],
    ]);
  });

  it("augmenter conserve les fichiers, diminuer signale les fichiers perdus", () => {
    const a = file("a.pdf");
    const start = [{ offre: [a], cga: [], autre: [] }, { offre: [file("b.pdf")], cga: [file("c.pdf")], autre: [] }];
    const up = resizeVariantes(start, 3);
    expect(up.variantes[0].offre[0]).toBe(a);
    expect(up.fichiersPerdus).toBe(0);
    const down = resizeVariantes(start, 1);
    expect(down.variantes).toHaveLength(1);
    expect(down.fichiersPerdus).toBe(2);
    expect(down.variantesRetirees).toBe(1);
  });

  it("exige l'Offre pour chaque variante, CGA facultatives", () => {
    expect(variantesManquantes([{ offre: [file("o")], cga: [], autre: [] }])).toEqual([]);
    expect(variantesManquantes([{ offre: [], cga: [file("c")], autre: [] }])).toEqual(["Variante 1 : Offre"]);
  });

  it("envoie chaque fichier sous le champ de sa variante", () => {
    const fd = variantesFormData({
      compagnie: "AXA",
      dateReception: "2026-11-05",
      clientToken: "tok",
      variantes: [
        { offre: [file("o1.pdf")], cga: [file("c1.pdf")], autre: [] },
        { offre: [file("o2.pdf")], cga: [file("c2.pdf")], autre: [file("a2.pdf")] },
      ],
    });
    expect(fd.get("parcours")).toBe(PARCOURS_REPONSES);
    expect(fd.get("nb_variantes")).toBe("2");
    expect(fd.get("variante_2_autre").name).toBe("a2.pdf");
    expect(fd.get("variante_1_cga").name).toBe("c1.pdf");
    expect(fd.get("client_token")).toBe("tok");
  });

  it("regroupe les documents par variante à l'affichage", () => {
    const groups = documentsParVariante({
      documents: [
        { id: "1", variante: 1, transmission_id: "t1" },
        { id: "2", variante: 2, transmission_id: "t1" },
        { id: "3", variante: 1, transmission_id: "t1" },
        { id: "4" },
      ],
    });
    expect(groups.map((g) => [g.variante, g.documents.map((d) => d.id)])).toEqual([
      [1, ["1", "3"]], [2, ["2"]], [0, ["4"]],
    ]);
  });
});

describe("deux parcours distincts", () => {
  it("Traitement : Compagnie, Date, Offre, CGA, Autre document, Commentaire", () => {
    expect(PARCOURS_FIELDS[PARCOURS_TRAITEMENT]).toEqual([
      "compagnie", "date_reception", "offre", "cga", "autre", "commentaire",
    ]);
    expect(traitementManquantes({ offre: [file("o.pdf")], cga: [], autre: [] })).toEqual([]);
    expect(traitementManquantes({ offre: [], cga: [file("c.pdf")], autre: [] })).toEqual(["Offre"]);
    const fd = traitementFormData({
      compagnie: "Zurich",
      dateReception: "2026-11-05",
      pieces: { offre: [file("z-offre.pdf")], cga: [file("z-cga.pdf")], autre: [file("z-autre.pdf")] },
      commentaire: " ok ",
    });
    expect(Array.from(fd.keys()).sort()).toEqual(["autre", "cga", "commentaires", "compagnie", "date_reception", "offre", "parcours"]);
    expect(fd.get("parcours")).toBe(PARCOURS_TRAITEMENT);
    expect(fd.get("offre").name).toBe("z-offre.pdf");
    expect(fd.get("cga").name).toBe("z-cga.pdf");
    const dialogs = src("components/TransmettreOffreDialogs.js");
    const simple = dialogs.slice(dialogs.indexOf("export function TransmettreOffreSimpleDialog"));
    expect(simple).toMatch(/simple-\$\{piece\.id\}/);
    expect(simple).toMatch(/VARIANTE_PIECES\.map/);
    expect(simple).toMatch(/data-testid="simple-pieces"/);
    expect(simple).toMatch(/traitementManquantes/);
    expect(simple).not.toMatch(/Référence|Montant|Garanties|Durée|Type de contrat|Nombre de variantes/);
  });

  it("le message suit l'état partiel ou complet calculé par l'API", () => {
    expect(messageTransmission({ transmission: { etat: "partielle", nb_transmises: 1, nb_sollicitees: 3 } }))
      .toBe("Offres partiellement transmises à l'agent (1/3 compagnies)");
    expect(messageTransmission({ transmission: { etat: "complete" } })).toBe("Offres transmises à l'agent");
    expect(messageTransmission({ transmission_deja_enregistree: true })).toBe("Transmission déjà enregistrée");
  });

  it("Réponses compagnies et Traitement ne sont pas le même formulaire", () => {
    expect(PARCOURS_FIELDS[PARCOURS_REPONSES]).not.toEqual(PARCOURS_FIELDS[PARCOURS_TRAITEMENT]);
    const fiche = src("pages/DemandeOffreFiche.js");
    expect(fiche).toMatch(/onAddOffer=\{openTransmitVariantes\}/);
    expect(fiche).toMatch(/onOffer=\{\(\) => setSimpleOfferOpen\(true\)\}/);
    expect(fiche).toMatch(/<TransmettreVariantesDialog/);
    expect(fiche).toMatch(/<TransmettreOffreSimpleDialog/);
    expect(fiche).not.toMatch(/>\s*Offre reçue\s*</);
  });
});

describe("file à traiter et bouton erreur", () => {
  it("met l'agent en première colonne, en gras, et le client en police normale", () => {
    expect(FILE_COLUMNS[0]).toBe("Agent");
    expect(FILE_COLUMNS[1]).toBe("Client");
    const page = src("pages/GestionReponsesOffres.js");
    const agent = page.indexOf('data-testid="file-agent"');
    const client = page.indexOf('data-testid="file-client"');
    expect(agent).toBeGreaterThan(-1);
    expect(agent).toBeLessThan(client);
    expect(page.slice(page.lastIndexOf("<td", agent), agent)).toMatch(/font-bold/);
    expect(page.slice(page.lastIndexOf("<td", client), client)).toMatch(/font-normal/);
  });

  it("urgence agent (Priorité Normal) passe devant priorité système Urgent", () => {
    const rows = [
      { id: "sys-urgent", urgente: false, priorite: "urgent", updated_at: "2026-11-09T12:00:00" },
      { id: "agent-urgent-normal", urgente: true, priorite: "normal", updated_at: "2026-11-06T08:00:00" },
      { id: "autre", urgente: false, priorite: "surveiller", updated_at: "2026-11-08T10:00:00" },
    ];
    expect(sortFileATraiter(rows).map((r) => r.id)).toEqual([
      "agent-urgent-normal",
      "sys-urgent",
      "autre",
    ]);
    expect(urgentesAgentEnTete(rows).map((r) => r.id)[0]).toBe("agent-urgent-normal");
    const page = src("pages/GestionReponsesOffres.js");
    expect(page).toMatch(/sortFileATraiter/);
    expect(page).toMatch(/urgentesAgentEnTete/);
  });

  it("une transmission partielle reste dans la file, la complète en sort", () => {
    const partielle = { statut: "Demande envoyée", etape_suivi: "offres_partielles", etape_suivi_label: "Offres partiellement transmises à l'agent" };
    expect(avancementCode(partielle)).not.toBe("offre_transmise");
    expect(avancementLabel(partielle)).toBe("Offres partiellement transmises à l'agent");
    expect(src("pages/GestionReponsesOffres.js")).toMatch(/avancementCode\(row\) === "offre_transmise"/);
  });

  it("Offres partiellement transmises est sélectionnable manuellement dans Avancement", () => {
    const fiche = src("pages/DemandeOffreFiche.js");
    expect(fiche).toMatch(/id: "offres_partielles"/);
    expect(fiche).not.toMatch(/id: "offres_partielles"[^\}]*auto:\s*true/);
    expect(fiche).toMatch(/SUIVI_IMMEDIAT/);
    expect(fiche).toMatch(/"offres_partielles"/);
    const optionMap = fiche.slice(fiche.indexOf("SUIVI_MENU.map"), fiche.indexOf("SUIVI_MENU.map") + 220);
    expect(optionMap).not.toMatch(/disabled=\{item\.auto\}/);
  });

  it("Signaler une erreur : fond blanc, texte foncé, même action", () => {
    expect(SIGNALER_ERREUR_CLASS).toMatch(/bg-white/);
    expect(SIGNALER_ERREUR_CLASS).toMatch(/text-slate-900/);
    expect(SIGNALER_ERREUR_CLASS).not.toMatch(/rose|red/);
    const fiche = src("pages/DemandeOffreFiche.js");
    expect(fiche).toMatch(/className=\{SIGNALER_ERREUR_CLASS\} onClick=\{onErreurs\}/);
    expect(fiche).toMatch(/Signaler une erreur/);
  });
});

describe("urgence sous 24 h", () => {
  it("refuse sans case puis sans motif", () => {
    expect(urgenceRefus({ delai24h: false, motif: "Client pressé" })).toMatch(/24 h/);
    expect(urgenceRefus({ delai24h: true, motif: "  " })).toMatch(/motif/);
    expect(urgenceRefus({ delai24h: true, motif: "Signature vendredi" })).toBe("");
  });

  it("affiche moins de 24 heures pour une urgence confirmée seulement", () => {
    expect(urgenceDelaiLabel({ urgente: true, urgence_delai: "moins_24h" })).toMatch(/moins de 24 heures/);
    expect(urgenceDelaiLabel({ urgente: true })).toBe("");
  });
});
