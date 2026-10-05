export function getDashboardTarget(key) {
  switch (key) {
    case 'nouveaux':
      return { path: '/dossiers', search: '?statut=Nouveau' };
    case 'attente-docs':
      return { path: '/dossiers', search: '?statut=Documents%20en%20attente' };
    case 'analyse':
      return { path: '/dossiers', search: '?statut=Analyse%20en%20cours' };
    case 'stand-by':
      return { path: '/dossiers', search: '?statut=Stand-by' };
    case 'presenter':
      return { path: '/dossiers', search: '?statut=%C3%80%20pr%C3%A9senter' };
    case 'termines':
      return { path: '/dossiers', search: '?statut=Cl%C3%B4tur%C3%A9' };
    case 'urgent':
      return { path: '/dossiers', search: '?priorite=urgent' };
    case 'taches':
      return { path: '/agenda' };
    case 'total':
      return { path: '/dossiers' };
    // Suivi 3e pilier
    case '3p-total':
      return { path: '/suivi-3p' };
    case '3p-analyses':
      return { path: '/suivi-3p', search: '?filtre=analyses' };
    case '3p-contactes':
      return { path: '/suivi-3p', search: '?filtre=contactes' };
    case '3p-a-contacter':
      return { path: '/suivi-3p', search: '?filtre=a_contacter' };
    case '3p-rdv':
      return { path: '/suivi-3p', search: '?filtre=rdv' };
    case '3p-signes':
      return { path: '/suivi-3p', search: '?statut=Sign%C3%A9' };
    case '3p-offres':
      return { path: '/suivi-3p', search: '?statut=Offre%20envoy%C3%A9e' };
    // Demandes d'offres
    case 'offres-total':
      return { path: '/demandes-offres' };
    case 'offres-brouillons':
      return { path: '/demandes-offres', search: '?statut=Brouillon' };
    case 'offres-attente':
      return { path: '/demandes-offres', search: '?filtre=en_attente' };
    case 'offres-recues':
      return { path: '/demandes-offres', search: '?filtre=offres_recues' };
    case 'offres-envoyees':
      return { path: '/demandes-offres', search: '?filtre=offres_envoyees' };
    case 'offres-signees':
      return { path: '/demandes-offres', search: '?filtre=signees' };
    case 'offres-variantes':
      return { path: '/demandes-offres' };
    default:
      return { path: '/dossiers' };
  }
}
