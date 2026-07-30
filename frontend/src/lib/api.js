import axios from "axios";

const getApiBaseUrl = () => {
  if (process.env.REACT_APP_API_URL) {
    return process.env.REACT_APP_API_URL;
  }

  if (typeof window !== "undefined" && window.location.hostname === "localhost") {
    return "http://localhost:8000/api";
  }

  return "/api";
};

const apiBaseUrl = getApiBaseUrl();

// #region agent log
if (typeof window !== "undefined") {
  fetch("http://127.0.0.1:7823/ingest/ab1b10fc-23b9-4892-bcb8-eb93db856015", {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-Debug-Session-Id": "5656aa" },
    body: JSON.stringify({
      sessionId: "5656aa",
      runId: "deploy-verify",
      hypothesisId: "H1-api-base",
      location: "frontend/src/lib/api.js",
      message: "API base URL resolved",
      data: { apiBaseUrl, host: window.location.hostname, href: window.location.href },
      timestamp: Date.now(),
    }),
  }).catch(() => {});
}
// #endregion

const api = axios.create({
  baseURL: apiBaseUrl,
  withCredentials: true,
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error?.response?.status === 401) {
      const path = typeof window !== "undefined" ? window.location.pathname : "";
      if (path && path !== "/login") {
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export { apiBaseUrl };
export default api;