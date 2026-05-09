import axios from "axios";

const API_BASE =
  process.env.REACT_APP_API_BASE || "http://localhost:5000";

const api = axios.create({ baseURL: API_BASE, timeout: 60000 });

api.interceptors.request.use((config) => {
  try {
    const stored = localStorage.getItem("invoice_auth");
    if (stored) {
      const { token } = JSON.parse(stored);
      if (token) config.headers.Authorization = `Bearer ${token}`;
    }
  } catch {}
  return config;
});

api.interceptors.response.use(
  (r) => r,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem("invoice_auth");
      window.location.href = "/signin";
    }
    return Promise.reject(err);
  }
);

export default api;
export { API_BASE };
