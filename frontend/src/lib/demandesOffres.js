/** Constantes et helpers UI du module Demandes d'offres 3P. */
import { formatDateFr, toIsoDate, toSwissDate } from "./dates";

export { formatDateFr, toIsoDate, toSwissDate };
export const STATUTS = [
  "Brouillon",
  "Demande validée",
  "Demande envoyée",
  "Demande incomplète",
  "En attente d'informations",
  "Offre reçue",
  "Offres complètes",
  "Offre à modifier",
  "Offre modifiée",
  "Offre choisie",
  "En conclusion",
  "Offre envoyée au client",
  "Offre signée",
  "Offre refusée",
  "Demande annulée",
];

/** Colonnes pipeline (alignées backend) — parcours suivi principal. */
export const KANBAN_COLUMNS = [
  "Brouillon",
  "Demande envoyée",
  "En attente d'informations",
  "Demande incomplète",
  "Offre reçue",
  "Offres complètes",
  "Offre à modifier",
  "Offre modifiée",
  "Offre choisie",
  "En conclusion",
  "Offre envoyée au client",
  "Offre signée",
];

export const STATUT_STYLE = {
  Brouillon: "bg-slate-500/10 text-slate-700 ring-1 ring-inset ring-slate-500/20",
  "Demande validée": "bg-blue-500/10 text-blue-800 ring-1 ring-inset ring-blue-500/25",
  "Demande envoyée": "bg-sky-500/10 text-sky-800 ring-1 ring-inset ring-sky-500/25",
  "Demande incomplète": "bg-rose-500/10 text-rose-800 ring-1 ring-inset ring-rose-500/25",
  "En attente d'informations": "bg-orange-500/10 text-orange-800 ring-1 ring-inset ring-orange-500/25",
  "Offre reçue": "bg-violet-500/10 text-violet-800 ring-1 ring-inset ring-violet-500/25",
  "Offres complètes": "bg-emerald-500/10 text-emerald-800 ring-1 ring-inset ring-emerald-500/25",
  "Offre complète": "bg-emerald-500/10 text-emerald-800 ring-1 ring-inset ring-emerald-500/25",
  "Offre à modifier": "bg-amber-500/10 text-amber-900 ring-1 ring-inset ring-amber-500/30",
  "Offre modifiée": "bg-teal-500/10 text-teal-800 ring-1 ring-inset ring-teal-500/25",
  "Offre choisie": "bg-indigo-500/10 text-indigo-800 ring-1 ring-inset ring-indigo-500/25",
  "En conclusion": "bg-fuchsia-500/10 text-fuchsia-800 ring-1 ring-inset ring-fuchsia-500/25",
  "Offre envoyée au client": "bg-amber-500/10 text-amber-800 ring-1 ring-inset ring-amber-500/25",
  "Offre signée": "bg-emerald-500/10 text-emerald-800 ring-1 ring-inset ring-emerald-500/25",
  "Offre refusée": "bg-red-500/10 text-red-800 ring-1 ring-inset ring-red-500/25",
  "Demande annulée": "bg-zinc-500/10 text-zinc-600 ring-1 ring-inset ring-zinc-500/20",
};

export const COMPAGNIES_DEFAUT = [
  "PAX", "Helvetia", "Swiss Life", "AXA", "Zurich", "Generali", "Baloise",
  "Allianz", "Vaudoise", "Mobilière", "Groupe Mutuel", "Retraites Populaires",
  "Swica", "CSS", "Smile Direct",
];
export const ACTIVITES_RISQUE = [
  "Alpinisme / Escalade", "Aviation", "Canyonning", "Deltaplane / Parapente",
  "Équitation", "Kitesurf", "Parachutisme", "Plongée subaquatique sportive",
  "Ski / Snowboarding", "Spéléologie", "Sport de combat", "Sports mécaniques",
  "Voile", "Vol à voile",
];
export const TYPES_PILIER = ["Pilier lié 3a", "Pilier libre 3b"];
export const PERIODICITES = ["Mensuel", "Trimestriel", "Semestriel", "Annuel", "Prime unique"];
export const TYPES_PAIEMENT = [
  "BVR", "Débit direct", "LSV", "Compte de dépôt de prime fermé",
  "Compte de dépôt de prime ouvert", "Prime unique",
];
export const EXONERATIONS = ["Aucun", "3 mois", "6 mois", "12 mois", "24 mois"];
export const LANGUES = ["Français", "Allemand", "Italien", "Anglais"];
export const CIVILITES = ["Monsieur", "Madame"];
export const SEXES = ["Homme", "Femme"];
export const STATUTS_PRO = ["Salarié", "Indépendant", "Pas d'activité lucrative"];
export const SITUATIONS = ["Célibataire", "Marié(e)", "Veuf/Veuve"];
export const OUI_NON = ["Oui", "Non"];

/** Wizard legacy — compagnies juste après le client. */
export const STEPS = ["Client", "Compagnies", "Situation", "3e pilier", "Documents", "Vérification"];

export const TYPES_CLIENT = [
  { id: "existant", label: "Client existant" },
  { id: "nouveau", label: "Nouveau client" },
];

export const DEMANDE_ORIGINE = {
  conseiller: "conseiller",
  attribuee: "attribuee",
};

/** Libellés complets — distinction nette des 2 types de demandes. */
export const DEMANDE_ORIGINE_LABELS = {
  conseiller: "Demande d'offre – Conseiller",
  attribuee: "Demande d'offre attribuée",
};

/** Libellés courts pour badges. */
export const DEMANDE_ORIGINE_SHORT = {
  conseiller: "Conseiller",
  attribuee: "Attribuée",
};

export const DEMANDE_ORIGINE_STYLE = {
  conseiller: "bg-sky-50 text-sky-900 ring-1 ring-inset ring-sky-200",
  attribuee: "bg-indigo-50 text-indigo-900 ring-1 ring-inset ring-indigo-300",
};

export const DEMANDE_ORIGINE_FILTERS = [
  { id: "all", label: "Toutes les demandes" },
  { id: "conseiller", label: "Demandes conseiller", short: "Conseiller" },
  { id: "attribuee", label: "Demandes attribuées", short: "Attribuées" },
];

/** Catalogue d'erreurs pour marquage « offre incomplète » (aligné backend). */
export const ERREURS_INCOMPLETE_CATALOG = [
  { code: "document_manquant", label: "Document manquant" },
  { code: "info_client_manquante", label: "Information client manquante" },
  { code: "signature_manquante", label: "Signature manquante" },
  { code: "champ_vide", label: "Champ non rempli" },
  { code: "mauvaise_info", label: "Mauvaise information" },
  { code: "mauvais_formulaire", label: "Mauvais formulaire" },
  { code: "autre", label: "Autre" },
];

export function erreurLabel(code) {
  return ERREURS_INCOMPLETE_CATALOG.find((e) => e.code === code)?.label || code || "—";
}

export function demandeOrigineKey(origine) {
  const key = String(origine || "").toLowerCase();
  return key === DEMANDE_ORIGINE.attribuee ? DEMANDE_ORIGINE.attribuee : DEMANDE_ORIGINE.conseiller;
}

export function demandeOrigineLabel(origine) {
  return DEMANDE_ORIGINE_LABELS[demandeOrigineKey(origine)] || DEMANDE_ORIGINE_LABELS.conseiller;
}

export function demandeOrigineShort(origine) {
  return DEMANDE_ORIGINE_SHORT[demandeOrigineKey(origine)] || DEMANDE_ORIGINE_SHORT.conseiller;
}

export function isDemandeAttribuee(row) {
  return demandeOrigineKey(row?.demande_origine ?? row) === DEMANDE_ORIGINE.attribuee;
}

export function typeClientLabel(value) {
  if (value === "existant") return "Client existant";
  if (value === "nouveau") return "Nouveau client";
  return value || "—";
}

/** Champs comparés lors d'une modification d'offre. */
export const MODIFICATION_COMPARE_FIELDS = [
  { key: "civilite", label: "Civilité" },
  { key: "prenom", label: "Prénom" },
  { key: "nom", label: "Nom" },
  { key: "sexe", label: "Sexe" },
  { key: "date_naissance", label: "Date de naissance" },
  { key: "nationalite", label: "Nationalité" },
  { key: "permis", label: "Permis" },
  { key: "adresse", label: "Adresse" },
  { key: "ville", label: "Ville" },
  { key: "npa", label: "NPA" },
  { key: "pays", label: "Pays" },
  { key: "statut_professionnel", label: "Statut professionnel" },
  { key: "profession", label: "Profession" },
  { key: "type_pilier", label: "Type de pilier" },
  { key: "date_debut", label: "Date de début" },
  { key: "duree_contrat", label: "Durée du contrat" },
  { key: "montant_prime", label: "Montant prime" },
  { key: "periodicite_prime", label: "Périodicité" },
  { key: "rente_invalidite", label: "Rente invalidité / mensuelle" },
  { key: "langue_offre", label: "Langue de l'offre" },
  { key: "commentaires", label: "Commentaires" },
];

/** Catalogue de secours pour l'onglet Modifier une offre (si l'API menu est indisponible). */
export const OFFRES_FORM_MENU_FALLBACK = {
  title: "Offres",
  families: [
    {
      id: "particulier",
      label: "Assurances particulier",
      sections: [
        {
          id: "pilier3",
          label: "Formulaires 3ème pilier",
          items: [
            { label: "3ème pilier", form_type: "pilier3" },
            { label: "3ème pilier parent-enfant", form_type: "pilier3_parent_enfant" },
            { label: "3ème pilier risque pur", form_type: "pilier3_risque_pur" },
          ],
        },
        {
          id: "choses",
          label: "Formulaires choses",
          items: [
            { label: "Bâtiment", form_type: "assurances_particulier" },
            { label: "RC seule", form_type: "menage_rc" },
            { label: "RC-Ménage", form_type: "menage_rc" },
            { label: "Motocycles", form_type: "motocycle" },
            { label: "Véhicule", form_type: "vehicule" },
            { label: "Véhicule plaques interchangeables", form_type: "voyage" },
            { label: "Attestation Véhicule uniquement", form_type: "attestation_vehicule" },
          ],
        },
        {
          id: "autres_particulier",
          label: "Autres assurances pour particulier",
          items: [
            { label: "Maladie (Non CICERO)", form_type: "pilier3_autre" },
            { label: "Animaux", form_type: "animaux" },
            { label: "LAA employée de maison", form_type: "laa_employee_maison" },
            { label: "Protection juridique privé", form_type: "protection_juridique_particulier" },
          ],
        },
      ],
    },
    {
      id: "professionnelles",
      label: "Assurances professionnelles",
      sections: [
        {
          id: "complets",
          label: "Formulaires complets",
          items: [
            { label: "Entreprise COMPLET", form_type: "entreprise", subtitle: "RC pro, assurances choses et assurance de personnes employées" },
            { label: "Indépendant COMPLET", form_type: "formulaire_complet", subtitle: "RC pro, PGM, LAAF et rente invalidité" },
          ],
        },
        {
          id: "autres_pro",
          label: "Autres formulaires pro",
          items: [
            { label: "Assurance chef d'entreprise", form_type: "entreprise_31" },
            { label: "Assurance de personne employée", form_type: "entreprise_32" },
            { label: "La prévoyance professionnelle (LPP)", form_type: "entreprise_46" },
            { label: "LAAF / LAAC", form_type: "entreprise_28" },
            { label: "Perte de gain", form_type: "entreprise_27" },
            { label: "Rente invalidité", form_type: "entreprise_29" },
            { label: "Responsabilité civile", form_type: "rc_entreprise" },
            { label: "Assurances choses", form_type: "entreprise_33" },
            { label: "Véhicule entreprise", form_type: "entreprise_offres" },
            { label: "Véhicule entreprise plaques interchangeables", form_type: "entreprise_50" },
            { label: "Protection juridique ENTREPRISE", form_type: "protection_juridique_entreprise" },
            { label: "Protection juridique INDÉPENDANT", form_type: "protection_juridique_entreprise_2" },
          ],
        },
      ],
    },
  ],
};

/** Filtres de période pour statistiques & listes */
export const PERIODE_FILTERS = [
  { id: "all", label: "Toute période" },
  { id: "today", label: "Aujourd'hui" },
  { id: "week", label: "Cette semaine" },
  { id: "month", label: "Mois en cours" },
  { id: "last_month", label: "Mois dernier" },
  { id: "6months", label: "6 derniers mois" },
  { id: "year", label: "1 dernière année" },
  { id: "custom", label: "Période personnalisée" },
];

export function periodeLabel(id) {
  return PERIODE_FILTERS.find((p) => p.id === id)?.label || "Toute période";
}

export function formatVariantesSummary(row) {
  const n = row?.nb_variantes_sollicitees ?? (row?.compagnies?.length || 0);
  if (!n) return null;
  const comps = (row?.compagnies || []).slice(0, 3).join(", ");
  const extra = n > 3 ? ` +${n - 3}` : "";
  return `${n} variante${n > 1 ? "s" : ""}${comps ? ` · ${comps}${extra}` : ""}`;
}

export function formatChf(value) {
  if (value === null || value === undefined || value === "") return "—";
  const n = Number(value);
  if (Number.isNaN(n)) return "—";
  return new Intl.NumberFormat("fr-CH", {
    style: "currency",
    currency: "CHF",
    maximumFractionDigits: 0,
  }).format(n);
}

export function formatDateTimeFr(iso) {
  if (!iso) return "—";
  try {
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return formatDateFr(iso);
    return new Intl.DateTimeFormat("fr-CH", {
      day: "2-digit",
      month: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(d);
  } catch {
    return formatDateFr(iso);
  }
}

/** Libellés des types d'e-mails CRM. */
export const EMAIL_TYPE_LABELS = {
  demande_offre: "Demande d'offre",
  offre_recue: "Offre reçue",
  offres_completes: "Offres complètes",
  offre_incomplete: "Offre incomplète",
  offre_signee: "Offre signée",
  offre_modifiee: "Modification",
  rappel: "Rappel",
  dossier_presente: "Dossier présenté",
  smtp_test: "Test SMTP",
  notification: "Notification",
};

export function emailTypeLabel(type) {
  const key = String(type || "").toLowerCase();
  return EMAIL_TYPE_LABELS[key] || type || "E-mail";
}

/** Suffixe stocké dans form_payload pour une précision liée à un champ schéma. */
export const FIELD_COMMENT_SUFFIX = "__comment";

export function fieldCommentKey(name) {
  return `${name}${FIELD_COMMENT_SUFFIX}`;
}

/**
 * Champs pour lesquels une précision conseiller est utile au service Offres.
 * Aligné sur backend `field_allows_comment`.
 */
export function fieldAllowsComment(field) {
  if (!field || typeof field !== "object") return false;
  if (field.allow_comment === true) return true;
  if (field.allow_comment === false) return false;
  const type = field.type || "text";
  if (["section", "html", "file", "honeypot", "captcha", "hidden", "list", "textarea"].includes(type)) {
    return false;
  }
  const lab = String(field.label || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "");
  if (!lab) return false;
  if (lab.includes("commentaire") || lab.includes("renseignement complementaire") || lab.includes("informations complementaires")) {
    return false;
  }
  const hints = [
    "sinistre", "resiliation", "franchise", "garantie", "couverture", "motif",
    "pourquoi", "precision", "autre", "exclusion", "antecedent", "permis", "nationalite",
  ];
  if (["radio", "select", "checkbox"].includes(type) && hints.some((h) => lab.includes(h))) {
    return true;
  }
  return false;
}

/**
 * Préremplit identité / adresse du payload schéma depuis un client hub (éditable ensuite).
 */
export function prefillSchemaPayloadFromClient(schema, payload, client, { overwrite = false } = {}) {
  if (!schema?.fields?.length || !client) return payload || {};
  const next = { ...(payload || {}) };
  const crm = {
    civilite: client.civilite || client.sexe || "",
    prenom: client.prenom || "",
    nom: client.nom || "",
    sexe: client.sexe || "",
    date_naissance: client.date_naissance || "",
    nationalite: client.nationalite || "",
    permis: client.permis || "",
    adresse: client.adresse || "",
    adresse_ligne_2: client.adresse_complement || client.adresse_ligne_2 || "",
    ville: client.ville || "",
    npa: client.npa || "",
    pays: client.pays_residence || client.pays || "Suisse",
    email: client.email || "",
    telephone: client.telephone || "",
  };
  const fold = (s) => String(s || "")
    .toLowerCase()
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/\s+/g, " ")
    .trim();

  const roleFor = (lab, isAgent) => {
    if (isAgent) return null;
    if (lab.startsWith("civilite") || lab === "titre") return "civilite";
    if (lab === "prenom" || lab === "prenom :" || lab.includes("prenom du preneur") || lab.includes("prenom de l'assure") || lab.includes("prenom de l assure")) return "prenom";
    if (lab === "nom" || lab === "nom de famille" || lab === "nom :" || lab.includes("nom du preneur") || lab.includes("nom de l'assure") || lab.includes("nom de l assure")) return "nom";
    if (lab === "sexe") return "sexe";
    if (lab.includes("date de naissance") && !lab.includes("permis")) return "date_naissance";
    if (lab.startsWith("nationalite")) return "nationalite";
    if (lab === "permis" || lab.startsWith("permis de sejour")) return "permis";
    if (["adresse", "rue", "adresse postale"].includes(lab)) return "adresse";
    if (lab.includes("adresse ligne 2") || lab.includes("complement d adresse")) return "adresse_ligne_2";
    if (["ville", "localite"].includes(lab)) return "ville";
    if (["npa", "code postal", "cp"].includes(lab)) return "npa";
    if (["pays", "pays de residence"].includes(lab)) return "pays";
    if (lab === "telephone" || lab.startsWith("telephone") || lab === "tel" || lab === "mobile") return "telephone";
    if ((lab === "email" || lab === "e-mail" || lab === "courriel") && !lab.includes("agent") && !lab.includes("recevrez")) return "email";
    return null;
  };

  for (const field of schema.fields) {
    if (["section", "html", "file", "honeypot", "captcha", "hidden"].includes(field.type)) continue;
    const name = field.name || field.id;
    if (!name) continue;
    const lab = fold(field.label);
    const isAgent = lab.includes("agent") || lab.includes("conseiller") || lab.includes("votre adresse email") || lab.includes("votre numero finma");
    const role = roleFor(lab, isAgent);
    if (!role) continue;
    const val = String(crm[role] || "").trim();
    if (!val) continue;
    const cur = next[name];
    const empty = cur == null || cur === "" || (Array.isArray(cur) && !cur.length);
    if (empty || overwrite) next[name] = val;
  }
  return next;
}

/**
 * Construit un résumé des champs renseignés pertinents pour une demande d'offre.
 * Formulaires schéma : uniquement les champs du schéma (+ méta client/agent).
 * Legacy 3P : colonnes CRM du wizard.
 * N'inclut que les valeurs non vides.
 *
 * @param {object} demande
 * @param {{ schema?: object|null }} [options]
 */
export function buildDemandeResume(demande, options = {}) {
  if (!demande) return { sections: [], docs: [], rows: [] };
  const schema = options.schema || null;
  const filled = (v) => {
    if (v === null || v === undefined || v === false) return false;
    if (Array.isArray(v)) {
      if (!v.length) return false;
      if (typeof v[0] === "object") {
        return v.some((row) => Object.values(row || {}).some((x) => String(x ?? "").trim()));
      }
      return true;
    }
    if (typeof v === "string") return v.trim() !== "";
    return true;
  };
  const rows = [];
  const seen = new Set();
  const add = (label, value) => {
    if (!filled(value) || !label || seen.has(label)) return;
    seen.add(label);
    let display = value;
    if (Array.isArray(value)) {
      if (value.length && typeof value[0] === "object") {
        display = value
          .map((row) => Object.values(row || {}).filter((x) => String(x ?? "").trim()).join(" · "))
          .filter(Boolean)
          .join("\n");
      } else {
        display = value.join(", ");
      }
    }
    if (!filled(display)) return;
    rows.push({ label, value: display });
  };

  const formType = (demande.form_type || "pilier3_legacy").trim();
  const isSchemaForm = formType !== "pilier3_legacy";

  const clientName = `${demande.civilite || ""} ${demande.prenom || ""} ${demande.nom || ""}`.trim()
    || (demande.client_label && demande.client_label !== "—" ? demande.client_label : "");
  add("Client", clientName);
  add("Type de client", typeClientLabel(demande.type_client));
  add("Date de naissance", formatDateFr(demande.date_naissance) !== "—" ? formatDateFr(demande.date_naissance) : null);
  const adresse = [demande.adresse, [demande.npa, demande.ville].filter(Boolean).join(" "), demande.pays]
    .filter(Boolean)
    .join(", ");
  add("Adresse", adresse);
  add("Type d'offre", demande.form_type_label || (isSchemaForm ? null : demande.type_pilier));

  if (isSchemaForm) {
    const payload = demande.form_payload || {};
    const fields = (schema?.fields || []).filter(
      (f) => f.type !== "section" && f.type !== "html" && f.type !== "file" && f.type !== "honeypot" && f.type !== "captcha" && f.type !== "hidden",
    );
    // Résumé dynamique : labels / valeurs du schéma sélectionné uniquement
    for (const field of fields) {
      const name = field.name || field.id;
      if (!name) continue;
      // Visibilité show_when (même esprit qu'OffreSchemaForm)
      if (field.show_when?.rules?.length) {
        const sw = field.show_when;
        const results = sw.rules.map((rule) => {
          const raw = payload[rule.field];
          const expected = rule.value;
          if (Array.isArray(raw)) return raw.includes(expected);
          const actual = raw == null ? "" : String(raw);
          if (rule.op === "isnot") return actual !== expected;
          return actual === expected;
        });
        const ok = (sw.logic || "all") === "any" ? results.some(Boolean) : results.every(Boolean);
        if (!ok) continue;
      }
      const raw = payload[name];
      if (!filled(raw)) continue;
      const label = (field.label || "").trim() || name;
      // Ne jamais afficher un id technique comme libellé
      if (/^input[_\s.]?\d/i.test(label)) continue;
      add(label, field.type === "date" ? (formatDateFr(raw) !== "—" ? formatDateFr(raw) : toSwissDate(raw) || raw) : raw);
      const precision = payload[fieldCommentKey(name)];
      if (filled(precision)) add(`${label} — précision`, precision);
    }
  } else {
    // Wizard CRM legacy 3P uniquement
    add("Type de pilier", demande.type_pilier);
    add("Compagnies", demande.compagnies);
    if (filled(demande.montant_prime)) {
      add(
        "Montant / prime",
        `${formatChf(demande.montant_prime)}${demande.periodicite_prime ? ` · ${demande.periodicite_prime}` : ""}`,
      );
    }
    add("Date de début", formatDateFr(demande.date_debut) !== "—" ? formatDateFr(demande.date_debut) : null);
    add("Durée du contrat", demande.duree_contrat);
    add("Périodicité", !filled(demande.montant_prime) ? demande.periodicite_prime : null);
    add("Type de paiement", demande.type_paiement);
    add("Rente invalidité", demande.rente_invalidite);
    add("Exonération des primes", demande.exoneration_primes);
    add("Langue de l'offre", demande.langue_offre);

    const options = [];
    if (demande.inclure_cga) options.push("Inclure les CGA");
    if (demande.mandat_gestion) options.push("Mandat de gestion");
    if (demande.risque_pur && String(demande.risque_pur).toLowerCase() === "oui") options.push("Risque pur");
    if (demande.adaptation_auto_primes && String(demande.adaptation_auto_primes).toLowerCase() === "oui") {
      options.push("Adaptation auto. des primes");
    }
    if (demande.activites_risque && (demande.activites_risque_liste || []).length) {
      options.push(`Activités à risque : ${(demande.activites_risque_liste || []).join(", ")}`);
    }
    add("Options demandées", options.length ? options.join(" · ") : null);
  }

  add("Commentaires / informations complémentaires", demande.commentaires || demande.note_service_offre || (!isSchemaForm ? demande.renseignements_complementaires : null));
  add("Conseiller", demande.agent_label);
  add("Date d'envoi", formatDateFr(demande.date_envoi) !== "—" ? formatDateFr(demande.date_envoi) : null);
  add("N° demande", demande.numero);

  const docs = (demande.documents || []).map((d) => ({
    id: d.id,
    name: d.original_filename || d.filename || "Document",
    category: d.category || "",
  }));

  const sections = [{ title: "Résumé de la demande", rows }];
  return { sections, docs, rows };
}


/** Catégories d'affichage espace gestionnaire (alignées backend). */
export const GESTION_KPI_CARDS = [
  { id: "a_traiter", label: "Demandes à traiter", emoji: "📥", color: "bg-sky-50 border-sky-200 text-sky-900" },
  { id: "attribuees", label: "Demandes d'offre attribuées", emoji: "🏷️", color: "bg-indigo-50 border-indigo-200 text-indigo-900" },
  { id: "envoyees", label: "Demandes conseiller envoyées", emoji: "📤", color: "bg-blue-50 border-blue-200 text-blue-900" },
  { id: "en_attente", label: "En attente de réponse", emoji: "⏳", color: "bg-amber-50 border-amber-200 text-amber-900" },
  { id: "incompletes", label: "Offres incomplètes", emoji: "⚠️", color: "bg-rose-50 border-rose-200 text-rose-900" },
  { id: "offres_recues", label: "Offres reçues", emoji: "📄", color: "bg-violet-50 border-violet-200 text-violet-900" },
  { id: "a_modifier", label: "Offres à modifier", emoji: "✏️", color: "bg-amber-50 border-amber-200 text-amber-950" },
  { id: "modifiees", label: "Offres modifiées", emoji: "🔄", color: "bg-teal-50 border-teal-200 text-teal-900" },
  { id: "completes", label: "Offres complètes", emoji: "✅", color: "bg-emerald-50 border-emerald-200 text-emerald-900" },
  { id: "attente_signature", label: "En attente de signature", emoji: "✍️", color: "bg-fuchsia-50 border-fuchsia-200 text-fuchsia-900" },
  { id: "en_retard", label: "En retard", emoji: "🔴", color: "bg-red-50 border-red-200 text-red-900" },
];

export const GESTION_KANBAN_FALLBACK = [
  { id: "a_traiter", label: "À traiter", statuts: ["Demande envoyée", "Demande validée"] },
  { id: "en_attente", label: "En attente", statuts: ["En attente d'informations"] },
  { id: "incompletes", label: "Incomplètes", statuts: ["Demande incomplète"] },
  { id: "offres_recues", label: "Offres reçues", statuts: ["Offre reçue"] },
  { id: "a_modifier", label: "À modifier", statuts: ["Offre à modifier"] },
  { id: "modifiees", label: "Modifiées", statuts: ["Offre modifiée"] },
  { id: "completes", label: "Complètes", statuts: ["Offres complètes", "Offre complète", "Offre choisie", "En conclusion"] },
  { id: "envoyee_client", label: "Chez le client", statuts: ["Offre envoyée au client"] },
  { id: "signees", label: "Signées", statuts: ["Offre signée"] },
];

export const PRIORITE_STYLE = {
  normal: "bg-emerald-500/15 text-emerald-800 ring-1 ring-inset ring-emerald-500/25",
  surveiller: "bg-amber-500/15 text-amber-900 ring-1 ring-inset ring-amber-500/30",
  urgent: "bg-red-500/15 text-red-800 ring-1 ring-inset ring-red-500/30",
};

export function prioriteLabel(niveau) {
  if (niveau === "urgent") return "Urgent";
  if (niveau === "surveiller") return "À surveiller";
  return "Normal";
}

export function clientLabel(row) {
  const name = `${row?.prenom || ""} ${row?.nom || ""}`.trim();
  return name || row?.client_label || "—";
}

export function valuesEqual(a, b) {
  if (Array.isArray(a) || Array.isArray(b)) {
    return JSON.stringify(a || []) === JSON.stringify(b || []);
  }
  if (a === null || a === undefined || a === "") {
    return b === null || b === undefined || b === "";
  }
  return String(a) === String(b);
}

export function buildModificationChanges(snapshot, current, fields = MODIFICATION_COMPARE_FIELDS) {
  const changes = [];
  for (const { key, label } of fields) {
    const oldVal = snapshot?.[key];
    const newVal = current?.[key];
    if (valuesEqual(oldVal, newVal)) continue;
    changes.push({ field: key, label, old: oldVal ?? null, new: newVal ?? null });
  }
  const oldComps = snapshot?.compagnies || [];
  const newComps = current?.compagnies || [];
  if (!valuesEqual(oldComps, newComps)) {
    changes.push({
      field: "compagnies",
      label: "Compagnies",
      old: oldComps,
      new: newComps,
    });
  }
  return changes;
}

export function emptyForm() {
  return {
    client_id: null,
    type_client: "",
    agent_prenom: "", agent_nom: "", agent_email: "", agent_finma: "",
    civilite: "", nom: "", prenom: "", sexe: "", date_naissance: "",
    nationalite: "Suisse", permis: "", adresse: "", ville: "", npa: "",
    pays: "Suisse", statut_professionnel: "", profession: "",
    travail_bureau_80: "", affilie_lpp: "", fumeur: "", situation: "",
    activites_risque: false, activites_risque_liste: [],
    type_pilier: "Pilier lié 3a", date_debut: "", periodicite_prime: "Mensuel",
    montant_prime: "", deja_piliers_pax: "", type_paiement: "",
    duree_contrat: "", age_terme: "", exoneration_primes: "Aucun",
    rente_invalidite: "", diplome: "", adaptation_auto_primes: "",
    risque_pur: "", taille: "", poids: "", renseignements_complementaires: "",
    compagnies: [], commentaires: "", inclure_cga: false,
    date_prochain_rdv: "", langue_offre: "Français", mandat_gestion: false,
  };
}
