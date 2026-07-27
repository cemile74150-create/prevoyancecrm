import { getDashboardTarget } from './dashboardRoutes';

describe('getDashboardTarget', () => {
  it('maps KPI cards to the dossiers view with the right filter', () => {
    expect(getDashboardTarget('nouveaux')).toEqual({ path: '/dossiers', search: '?statut=Nouveau' });
    expect(getDashboardTarget('analyse')).toEqual({ path: '/dossiers', search: '?statut=Analyse%20en%20cours' });
    expect(getDashboardTarget('urgent')).toEqual({ path: '/dossiers', search: '?priorite=urgent' });
    expect(getDashboardTarget('taches')).toEqual({ path: '/agenda' });
  });

  it('returns the default dossiers route for the total card', () => {
    expect(getDashboardTarget('total')).toEqual({ path: '/dossiers' });
  });
});
