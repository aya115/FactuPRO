import { useAuth } from "../contexts/AuthContext";
import ComptableDashboard from "./ComptableDashboard";
import SuperviseurDashboard from "./SuperviseurDashboard";
import AdminDashboard from "./AdminDashboard";

export default function DashboardRouter() {
  const { user, loading } = useAuth();

  if (loading) return null;
  if (!user) return null;

  const role = user.role;

  if (role === "comptable") {
    return <ComptableDashboard />;
  }

  if (role === "superviseur") {
    return <SuperviseurDashboard />;
  }

  if (role === "admin") {
    return <AdminDashboard />;
  }

  return <div>Accès non autorisé</div>;
}