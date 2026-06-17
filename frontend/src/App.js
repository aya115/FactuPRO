import React from "react";
import { Routes, Route, Navigate, useLocation } from "react-router-dom";
import Navbar from "./components/Navbar";
import InvoicesCards from "./components/InvoicesCards";
import InvoiceAssistantDashboard from "./components/InvoiceAssistantDashboard";
import MetricsPage from "./components/MetricsPage";
import SignIn from "./components/SignIn";
import SignUp from "./components/SignUp";
import ProtectedRoute from "./components/ProtectedRoute";
import Footer from "./components/Footer";
import "./App.css";
import DashboardRouter from "./pages/DashboardRouter";
import UsersAdmin from "./pages/UsersAdmin";
import LandingPage from "./pages/LandingPage";
import InvoiceDetail from "./components/InvoiceDetail";
import InvoiceCorrectionReview from "./pages/InvoiceCorrectionReview";
import PowerBIDashboard from "./pages/PowerBIDashboard";
import Messenger from "./pages/Messenger";
function App() {
  const { pathname } = useLocation();
  const isHome = pathname === "/";

  return (
    <div className="App">
      <Navbar />
      <main className={`App__main${isHome ? " App__main--home" : ""}`}>
        <Routes>
          <Route path="/signin" element={<SignIn />} />
          <Route path="/signup" element={<SignUp />} />
          <Route path="/" element={<LandingPage />} />
          <Route
            path="/invoices"
            element={
              <ProtectedRoute>
                <InvoicesCards />
              </ProtectedRoute>
            }
          />
          <Route
            path="/assistant"
            element={
              <ProtectedRoute>
                <InvoiceAssistantDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/metrics"
            element={
              <ProtectedRoute>
                <MetricsPage />
              </ProtectedRoute>
            }
          />
          <Route
            path="/dashboard"
            element={
              <ProtectedRoute>
                <DashboardRouter />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/users"
            element={
              <ProtectedRoute>
                <UsersAdmin />
              </ProtectedRoute>
            }
          />
          <Route
            path="/messages"
            element={
              <ProtectedRoute roles={["comptable", "superviseur"]}>
                <Messenger />
              </ProtectedRoute>
            }
          />
          <Route
            path="/analytics/bi"
            element={
              <ProtectedRoute roles={["admin", "superviseur"]}>
                <PowerBIDashboard />
              </ProtectedRoute>
            }
          />
          <Route
            path="/admin/powerbi-setup"
            element={<Navigate to="/dashboard" replace />}
          />
          <Route
            path="/invoice/:id"
            element={
              <ProtectedRoute>
                <InvoiceDetail />
              </ProtectedRoute>
            }
          />
          <Route
            path="/supervisor/review/:id"
            element={
              <ProtectedRoute>
                <InvoiceCorrectionReview />
              </ProtectedRoute>
            }
          />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </main>
      <Footer />
    </div>
  );
}

export default App;
