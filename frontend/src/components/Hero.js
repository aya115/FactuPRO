import React from "react";
import "./Hero.css";

export default function Hero() {
  return (
    <section className="hero" id="app">
      <div className="hero__illu" aria-hidden>
        <svg className="hero__svg" viewBox="0 0 280 200" fill="none" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <linearGradient id="heroGrad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#3b82f6" stopOpacity="0.4"/>
              <stop offset="100%" stopColor="#10b981" stopOpacity="0.2"/>
            </linearGradient>
            <filter id="heroGlow">
              <feGaussianBlur stdDeviation="8" result="blur"/>
              <feMerge>
                <feMergeNode in="blur"/>
                <feMergeNode in="SourceGraphic"/>
              </feMerge>
            </filter>
          </defs>
          <rect x="40" y="20" width="200" height="160" rx="12" fill="url(#heroGrad)" filter="url(#heroGlow)" opacity="0.9"/>
          <rect x="50" y="35" width="180" height="130" rx="8" stroke="rgba(255,255,255,0.35)" strokeWidth="2" fill="rgba(255,255,255,0.06)"/>
          <line x1="50" y1="65" x2="230" y2="65" stroke="rgba(255,255,255,0.2)" strokeWidth="1.5"/>
          <line x1="50" y1="95" x2="200" y2="95" stroke="rgba(255,255,255,0.15)" strokeWidth="1"/>
          <line x1="50" y1="120" x2="180" y2="120" stroke="rgba(255,255,255,0.15)" strokeWidth="1"/>
          <circle cx="220" cy="140" r="24" fill="rgba(59, 130, 246, 0.5)" stroke="rgba(255,255,255,0.4)" strokeWidth="2"/>
          <path d="M212 140l6 6 12-12" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" fill="none"/>
        </svg>
      </div>
      <span className="hero__badge">Powered by IA · OCR + LLM</span>
      <h1 className="hero__title">Plateforme Factures IA</h1>
      <p className="hero__subtitle">Extraction et classification intelligente de vos factures</p>
    </section>
  );
}
