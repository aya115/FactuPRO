import { render, screen } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { AuthProvider } from "./contexts/AuthContext";
import App from "./App";

function renderApp() {
  return render(
    <BrowserRouter>
      <AuthProvider>
        <App />
      </AuthProvider>
    </BrowserRouter>
  );
}

test("affiche la page d accueil", () => {
  renderApp();
  expect(
    screen.getByText(/Gérez vos factures avec/i)
  ).toBeInTheDocument();
});
