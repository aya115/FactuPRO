import { Navigate, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";

function normalizeRole(role) {
  return (role || "").toString().trim().toLowerCase();
}

export default function ProtectedRoute({ children, roles }) {
  const { isAuthenticated, loading, user } = useAuth();
  const location = useLocation();

  if (loading) {
    return <div className="role-route-loading">Chargement…</div>;
  }

  if (!isAuthenticated) {
    return <Navigate to="/signin" state={{ from: location }} replace />;
  }

  if (roles?.length) {
    const role = normalizeRole(user?.role);

    if (!role) {
      return <div className="role-route-loading">Chargement…</div>;
    }

    const allowed = roles.map(normalizeRole);
    if (role !== "admin" && !allowed.includes(role)) {
      return <Navigate to="/dashboard" replace />;
    }
  }

  return children;
}
