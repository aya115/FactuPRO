import { useEffect } from "react";
import { Link, useLocation } from "react-router-dom";
import { useAuth } from "../contexts/AuthContext";
import "./LandingPage.css";

export default function LandingPage() {
  const { isAuthenticated } = useAuth();
  const location = useLocation();

  useEffect(() => {
    const scrollTo = location.state?.scrollTo;
    if (scrollTo) {
      const el = document.getElementById(scrollTo);
      if (el) el.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }, [location.state?.scrollTo]);

  return (
    <div className="home">
      {/* Hero */}
      <section className="home__hero">
        <div className="home__hero-content">
          
          <span className="home__badge">Powered by IA · OCR & LLM</span>
          <h1 className="home__hero-title">
            Gérez vos factures avec l&apos;intelligence artificielle
          </h1>
          <p className="home__hero-subtitle">
            Extraction automatique, classification et analyse de vos documents comptables.
            Gagnez du temps et réduisez les erreurs.
          </p>
          
        </div>
        <div className="home__hero-visual">
          <div className="home__hero-orbit home__hero-orbit--blue" />
          <div className="home__hero-orbit home__hero-orbit--pink" />
          <div className="home__hero-mockup">
            <div className="home__mockup-header">
              <span></span><span></span><span></span>
            </div>
            <div className="home__mockup-body">
              <div className="home__mockup-row" />
              <div className="home__mockup-row home__mockup-row--short" />
              <div className="home__mockup-row home__mockup-row--short" />
              <div className="home__mockup-row" />
              <div className="home__mockup-row home__mockup-row--short" />
            </div>
          </div>
        </div>
      </section>

      {/* Features */}
      <section id="fonctionnalites" className="home__features">
        <h2 className="home__section-title">Pourquoi choisir FactuPRO ?</h2>
        <div className="home__features-grid">
          <article className="home__feature">
            <div className="home__feature-icon">📄</div>
            <h3>OCR avancé</h3>
            <p>Extraction précise des données depuis PDF, images et scans. Reconnaissance des tableaux et structures complexes.</p>
          </article>
          <article className="home__feature">
            <div className="home__feature-icon">🤖</div>
            <h3>IA & LLM</h3>
            <p>Classification automatique par catégorie et compte comptable. L&apos;assistant IA vous aide dans vos analyses.</p>
          </article>
          <article className="home__feature">
            <div className="home__feature-icon">📊</div>
            <h3>Tableaux & métriques</h3>
            <p>Vue d&apos;ensemble en temps réel. Suivi de la précision OCR et des performances du pipeline.</p>
          </article>
        </div>
      </section>

      {/* Visual block with image */}
      <section id="automatisation" className="home__visual">
        <div className="home__visual-content">
          <h2>Automatisez votre compta</h2>
          <p>Uploadez vos factures, laissez l&apos;IA extraire et classifier les données, puis exportez ou consultez vos lignes en un clic.</p>
          <Link to={isAuthenticated ? "/dashboard" : "/signup"} className="home__btn home__btn--primary">
            Démarrer maintenant
          </Link>
        </div>
        <div className="home__visual-image">
          <img
            src="https://images.unsplash.com/photo-1554224155-8d04cb21cd6c?w=700&q=80"
            alt="Bureau et documents comptables"
            loading="lazy"
          />
        </div>
      </section>

      {/* CTA final */}
      <section id="demarrer" className="home__cta">
        <h2>Prêt à simplifier votre facturation ?</h2>
        <p>Rejoignez la plateforme et testez gratuitement.</p>
        <div className="home__cta-actions">
          {!isAuthenticated && (
            <>
              <Link to="/signin" className="home__btn home__btn--primary home__btn--lg">
                Se connecter
              </Link>
              <Link to="/signup" className="home__btn home__btn--outline home__btn--lg">
                S&apos;inscrire
              </Link>
            </>
          )}
          {isAuthenticated && (
            <Link to="/dashboard" className="home__btn home__btn--primary home__btn--lg">
              Accéder au tableau de bord
            </Link>
          )}
        </div>
      </section>
      {/* Contact Us */}
<section id="contact" className="home__contact">
  <h2>Contactez-nous</h2>
  <p>Besoin d’aide ? Envoyez-nous un message.</p>

  <form className="home__contact-form">
    <input type="text" placeholder="Nom" />
    <input type="email" placeholder="Email" />
    <textarea placeholder="Message" rows="5"></textarea>

    <button className="home__btn home__btn--primary">
      Envoyer
    </button>
  </form>
</section>
    </div>
  );
}
