import axios from "axios";
import {
  filenameFromContentDisposition,
  pickDownloadFilename,
} from "@/lib/downloadFilename";

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

const api = axios.create({
  baseURL: apiBaseUrl,
  withCredentials: true,
});

api.interceptors.response.use(
  (res) => res,
  (error) => {
    if (error?.response?.status === 401) {
      const path = typeof window !== "undefined" ? window.location.pathname : "";
      // Ne pas forcer /login pendant le boot auth : AuthContext gère déjà l'état.
      if (path && path !== "/login" && !path.startsWith("/login")) {
        const url = error?.config?.url || "";
        if (url.includes("/auth/me")) {
          return Promise.reject(error);
        }
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);

export {
  apiBaseUrl,
  openAuthenticatedBlob,
  downloadAuthenticatedBlob,
  downloadAuthenticatedPost,
  blobErrorMessage,
};
export default api;

function buildApiUrl(path) {
  const base = String(apiBaseUrl || "").replace(/\/$/, "");
  const p = path.startsWith("/") ? path : `/${path}`;
  if (base.startsWith("http://") || base.startsWith("https://")) {
    return `${base}${p}`;
  }
  if (typeof window !== "undefined" && window.location?.origin) {
    return `${window.location.origin}${base}${p}`;
  }
  return `${base}${p}`;
}

function isApiSameOrigin() {
  if (!String(apiBaseUrl || "").startsWith("http")) return true;
  if (typeof window === "undefined" || !window.location?.origin) return false;
  try {
    return new URL(apiBaseUrl).origin === window.location.origin;
  } catch {
    return false;
  }
}

/**
 * Ouvre un fichier via le backend authentifié (cookie/session).
 * En same-origin, navigation directe pour que « Enregistrer sous »
 * utilise Content-Disposition (nom d'origine) — pas l'UUID du blob:.
 */
async function openAuthenticatedBlob(path, filename) {
  if (isApiSameOrigin()) {
    window.open(buildApiUrl(path), "_blank", "noopener,noreferrer");
    return buildApiUrl(path);
  }
  const res = await api.get(path, { responseType: "blob" });
  const name = pickDownloadFilename(
    filenameFromContentDisposition(res.headers["content-disposition"], null),
    filename,
    "document.pdf"
  );
  const typed =
    res.data instanceof Blob && name
      ? new Blob([res.data], { type: res.data.type || "application/octet-stream" })
      : res.data;
  const url = URL.createObjectURL(typed);
  window.open(url, "_blank", "noopener,noreferrer");
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return url;
}

/**
 * Télécharge un fichier via le backend authentifié.
 * Le nom enregistré (argument filename / Content-Disposition) est conservé ;
 * les UUID / clés de stockage ne sont jamais utilisés comme nom de fichier.
 */
async function downloadAuthenticatedBlob(path, filename = "document.pdf") {
  const res = await api.get(path, { responseType: "blob" });
  const name = pickDownloadFilename(
    filenameFromContentDisposition(res.headers["content-disposition"], null),
    filename,
    "document.pdf"
  );
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return name;
}

async function blobErrorMessage(err, fallback) {
  const data = err?.response?.data;
  if (data instanceof Blob) {
    try {
      const text = await data.text();
      const parsed = JSON.parse(text);
      if (typeof parsed?.detail === "string") return parsed.detail;
    } catch {
      /* ignore */
    }
  }
  if (typeof err?.response?.data?.detail === "string") return err.response.data.detail;
  return fallback;
}

/**
 * Télécharge un fichier produit par un POST authentifié (docx / zip).
 */
async function downloadAuthenticatedPost(path, body, fallbackName = "document.docx") {
  const res = await api.post(path, body ?? {}, { responseType: "blob" });
  const filename = pickDownloadFilename(
    filenameFromContentDisposition(res.headers["content-disposition"], null),
    fallbackName,
    fallbackName
  );
  const url = URL.createObjectURL(res.data);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60_000);
  return filename;
}
