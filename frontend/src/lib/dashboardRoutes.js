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
    default:
      return { path: '/dossiers' };
  }
}
