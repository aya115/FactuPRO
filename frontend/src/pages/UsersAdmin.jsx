import { useCallback, useEffect, useState } from "react";
import api from "../api";
import { useAuth } from "../contexts/AuthContext";
import "./UsersAdmin.css";

export default function UsersAdmin() {
  const { getAuthHeader } = useAuth();
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);

  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState(null);

  const [formData, setFormData] = useState({
    email: "",
    password: "",
    full_name: "",
    role: "comptable"
  });

  // ================= LOAD USERS =================
  const loadUsers = useCallback(async () => {
    try {
      const res = await api.get("/admin/users", {
        headers: getAuthHeader()
      });
      setUsers(res.data.users || []);
    } catch (err) {
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [getAuthHeader]);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  // ================= CREATE OR UPDATE =================
  const handleSubmit = async () => {
    try {
      if (editingUser) {
        // UPDATE
        await api.put(
          `/admin/users/${editingUser.id}`,
          {
            full_name: formData.full_name,
            role: formData.role
          },
          { headers: getAuthHeader() }
        );
      } else {
        // CREATE
        await api.post(
          "/admin/users",
          formData,
          { headers: getAuthHeader() }
        );
      }

      resetForm();
      loadUsers();
    } catch (err) {
      console.error(err);
    }
  };

  // ================= DELETE =================
  const deleteUser = async (id) => {
    if (!window.confirm("Supprimer cet utilisateur ?")) return;

    try {
      await api.delete(`/admin/users/${id}`, {
        headers: getAuthHeader()
      });
      loadUsers();
    } catch (err) {
      console.error(err);
    }
  };

  // ================= EDIT =================
  const editUser = (user) => {
    setEditingUser(user);
    setFormData({
      email: user.email,
      password: "",
      full_name: user.full_name,
      role: user.role
    });
    setShowForm(true);
  };

  const resetForm = () => {
    setShowForm(false);
    setEditingUser(null);
    setFormData({
      email: "",
      password: "",
      full_name: "",
      role: "comptable"
    });
  };

  if (loading) return <p>Chargement...</p>;

  return (
    <div className="dashboard-container">
      <h1>👥 Gestion des utilisateurs</h1>

      <button className="btn-create" onClick={() => setShowForm(true)}>
         Créer utilisateur
      </button>

      {/* ================= MODAL ================= */}
      {showForm && (
        <div className="modal">
          <div className="modal-content">
            <h2>
              {editingUser ? "Modifier utilisateur" : "Créer utilisateur"}
            </h2>

            {!editingUser && (
              <>
                <input
                  type="email"
                  placeholder="Email"
                  value={formData.email}
                  onChange={(e) =>
                    setFormData({ ...formData, email: e.target.value })
                  }
                />

                <input
                  type="password"
                  placeholder="Mot de passe"
                  value={formData.password}
                  onChange={(e) =>
                    setFormData({ ...formData, password: e.target.value })
                  }
                />
              </>
            )}

            <input
              type="text"
              placeholder="Nom complet"
              value={formData.full_name}
              onChange={(e) =>
                setFormData({ ...formData, full_name: e.target.value })
              }
            />

            <select
              value={formData.role}
              onChange={(e) =>
                setFormData({ ...formData, role: e.target.value })
              }
            >
              <option value="comptable">Comptable</option>
              <option value="superviseur">Superviseur</option>
              <option value="admin">Admin</option>
            </select>

            <div className="modal-buttons">
              <button onClick={handleSubmit}>
                {editingUser ? "Mettre à jour" : "Créer"}
              </button>
              <button onClick={resetForm}>Annuler</button>
            </div>
          </div>
        </div>
      )}

      {/* ================= TABLE ================= */}
      <table className="users-table">
        <thead>
          <tr>
            <th>ID</th>
            <th>Email</th>
            <th>Nom</th>
            <th>Rôle</th>
            <th>Actions</th>
          </tr>
        </thead>

        <tbody>
          {users.map((user) => (
            <tr key={user.id}>
              <td>{user.id}</td>
              <td>{user.email}</td>
              <td>{user.full_name}</td>
              <td>
                <span className={`role-badge ${user.role}`}>
                  {user.role}
                </span>
              </td>
              <td>
                <button
                  className="btn-edit"
                  onClick={() => editUser(user)}
                >
                  Modifier
                </button>

                <button
                  className="btn-delete"
                  onClick={() => deleteUser(user.id)}
                >
                  Supprimer
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}