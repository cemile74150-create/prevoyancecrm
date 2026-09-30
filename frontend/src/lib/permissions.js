export const PERMISSION_CATALOG = [
  {
    id: "clients",
    label: "Clients",
    items: [
      { key: "clients.view", label: "Voir les clients" },
      { key: "clients.create", label: "Créer un client" },
      { key: "clients.edit", label: "Modifier un client" },
      { key: "clients.delete", label: "Supprimer un client" },
    ],
  },
  {
    id: "dossiers",
    label: "Dossiers",
    items: [
      { key: "dossiers.view", label: "Voir les dossiers" },
      { key: "dossiers.create", label: "Créer un dossier" },
      { key: "dossiers.edit", label: "Modifier un dossier" },
      { key: "dossiers.delete", label: "Supprimer un dossier" },
    ],
  },
  {
    id: "documents",
    label: "Documents",
    items: [
      { key: "documents.view", label: "Voir les documents" },
      { key: "documents.add", label: "Ajouter des documents" },
      { key: "documents.delete", label: "Supprimer des documents" },
    ],
  },
  {
    id: "suivi_3p",
    label: "Fiscalité, 3e pilier & Fortune 2026",
    items: [
      { key: "suivi_3p.view", label: "Voir le suivi 3e pilier" },
      { key: "suivi_3p.edit", label: "Modifier le suivi 3e pilier" },
    ],
  },
    {
    id: "demandes_offres",
    label: "Demandes d'offres 3P",
    items: [
      { key: "demandes_offres.view", label: "Voir les demandes d'offres" },
      { key: "demandes_offres.edit", label: "Créer/modifier les demandes d'offres" },
      { key: "demandes_offres.process", label: "Traiter les réponses aux offres (gestionnaire)" },
    ],
  },
  {
    id: "rappels",
    label: "Rappels",
    items: [
      { key: "rappels.view", label: "Voir les rappels" },
      { key: "rappels.edit", label: "Créer/modifier des rappels" },
    ],
  },
  {
    id: "agenda",
    label: "Ordre du jour",
    items: [
      { key: "agenda.view", label: "Voir l’ordre du jour" },
    ],
  },
  {
    id: "formulaires",
    label: "Formulaires",
    items: [
      { key: "formulaires.view", label: "Voir les formulaires" },
    ],
  },
  {
    id: "users",
    label: "Administration",
    items: [
      { key: "users.manage", label: "Gérer les utilisateurs" },
    ],
  },
];

export const PERMISSION_KEYS = PERMISSION_CATALOG.flatMap((g) => g.items.map((i) => i.key));

export function defaultPermissions(role) {
  const perms = Object.fromEntries(PERMISSION_KEYS.map((k) => [k, true]));
  if (role !== "admin") {
    perms["users.manage"] = false;
  }
  // Traitement offres : pas pour les conseillers par défaut
  if (role === "conseiller") {
    perms["demandes_offres.process"] = false;
  } else {
    perms["demandes_offres.process"] = true;
  }
  return perms;
}

export function defaultSeeAllDossiers(role) {
  return role === "admin" || role === "ceo" || role === "gestionnaire_offres";
}

export function hasPerm(user, key) {
  if (!user || !key) return false;
  if (user.permissions && typeof user.permissions === "object" && key in user.permissions) {
    return Boolean(user.permissions[key]);
  }
  const defaults = defaultPermissions(user.role);
  if (key in defaults) return Boolean(defaults[key]);
  if (key === "users.manage") {
    return user.role === "admin" || Boolean(user.can_manage_users);
  }
  return true;
}

export function canSeeAllDossiers(user) {
  if (!user) return false;
  if (user.see_all_dossiers === true) return true;
  if (user.see_all_dossiers === false) return false;
  return user.role === "admin" || user.role === "ceo" || user.role === "gestionnaire_offres";
}

export function dossierAccessLabel(user) {
  if (canSeeAllDossiers(user)) return "Tous les dossiers";
  const name = (user?.conseiller || user?.name || "").trim();
  return name ? `Dossiers de ${name}` : "Ses dossiers uniquement";
}

export function enabledPermissionCount(user) {
  const perms = user?.permissions || defaultPermissions(user?.role);
  return PERMISSION_KEYS.filter((k) => perms[k]).length;
}
