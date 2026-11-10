import api from "@/lib/api";

export const fetchEligibilityLists = () => api.get("/eligibility/lists").then((r) => r.data);

export const createEligibilityList = (name) =>
  api.post("/eligibility/lists", { name }).then((r) => r.data);

export const fetchEligibilityListClients = (listId, { q, page = 1, pageSize = 50 } = {}) =>
  api
    .get(`/eligibility/lists/${encodeURIComponent(listId)}/clients`, {
      params: { q: q || undefined, page, page_size: pageSize },
    })
    .then((r) => r.data);

export const fetchClientEligibility = (clientId) =>
  api.get(`/clients/${encodeURIComponent(clientId)}/eligibility`).then((r) => r.data);

export const saveClientEligibility = (clientId, listId, checked) => {
  const path = `/clients/${encodeURIComponent(clientId)}/eligibility/${encodeURIComponent(listId)}`;
  return (checked ? api.put(path) : api.delete(path)).then((r) => r.data);
};
