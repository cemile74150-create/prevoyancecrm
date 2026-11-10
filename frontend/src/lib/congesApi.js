import api from "@/lib/api";

const clean = (params) => Object.fromEntries(
  Object.entries(params || {}).filter(([, v]) => v !== undefined && v !== null && v !== "" && v !== "all"),
);

export const fetchLeavesMeta = async () => (await api.get("/leaves/meta")).data;
export const fetchMyLeaves = async (params) => (await api.get("/leaves/mine", { params: clean(params) })).data;
export const fetchAdminLeaves = async (params) => (await api.get("/leaves/admin", { params: clean(params) })).data;
export const fetchLeaveEmployees = async () => (await api.get("/leaves/employees")).data.items || [];
export const fetchLeave = async (id) => (await api.get(`/leaves/${id}`)).data;
export const fetchLeaveCalendar = async (params) => (await api.get("/leaves/calendar", { params: clean(params) })).data;
export const previewLeave = async (body) => (await api.post("/leaves/preview", body)).data;
export const createLeave = async (body) => (await api.post("/leaves", body)).data;
export const cancelLeave = async (id, body) => (await api.post(`/leaves/${id}/cancel`, body || {})).data;
export const requestLeaveCancellation = async (id, body) => (await api.post(`/leaves/${id}/request-cancellation`, body || {})).data;
export const approveLeave = async (id, body) => (await api.post(`/leaves/${id}/approve`, body || {})).data;
export const rejectLeave = async (id, body) => (await api.post(`/leaves/${id}/reject`, body)).data;
export const resolveLeaveCancellation = async (id, body) => (await api.post(`/leaves/${id}/resolve-cancellation`, body)).data;
