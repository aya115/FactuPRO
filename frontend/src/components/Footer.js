import React from "react";
import "./Footer.css";

export default function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <img
          className="footer__logo"
          src={`${process.env.PUBLIC_URL}/factupro-logo.png`}
          alt="FactuPRO"
          width={200}
          height={42}
        />
        <p className="footer__text">
          Plateforme d’automatisation Purchase-to-Pay · OCR · NLP · Classification supervisée
        </p>
      </div>
    </footer>
  );
}
