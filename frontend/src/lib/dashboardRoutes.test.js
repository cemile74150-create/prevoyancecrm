import { getDashboardTarget } from './dashboardRoutes';

describe('getDashboardTarget', () => {
  it('maps KPI cards to the dossiers view with the right filter', () => {
    expect(getDashboardTarget('nouveaux')).toEqual({ path: '/dossiers', search: '?statut=Nouveau' });
    expect(getDashboardTarget('attente-docs')).toEqual({ path: '/dossiers', search: '?statut=Documents%20en%20attente' });
    expect(getDashboardTarget('analyse')).toEqual({ path: '/dossiers', search: '?statut=Analyse%20en%20cours' });
    expect(getDashboardTarget('stand-by')).toEqual({ path: '/dossiers', search: '?statut=Stand-by' });
    expect(getDashboardTarget('presenter')).toEqual({ path: '/dossiers', search: '?statut=%C3%80%20pr%C3%A9senter' });
    expect(getDashboardTarget('urgent')).toEqual({ path: '/dossiers', search: '?priorite=urgent' });
    expect(getDashboardTarget('taches')).toEqual({ path: '/agenda' });
  });

  it('returns the default dossiers route for the total card', () => {
    expect(getDashboardTarget('total')).toEqual({ path: '/dossiers' });
  });
});
