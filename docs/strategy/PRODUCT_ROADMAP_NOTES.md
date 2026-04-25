# Mazao AI Product Roadmap & Strategy Notes

This document captures deferred architecture ideas, future financial product candidates, and UX patterns to maintain a lean, anti-overengineered core.

## 🛡️ Governance: Anti-Overengineering Rule
**Rule**: Finish and prove the market-fit of one financial product before adding another. No concurrent development of complex loan/credit products.

---

## 🏦 Future Financial Products (Deferred)

### M-Shwari Integration (Phase T6 Candidate)
*   **Status**: DEFERRED.
*   **Objective**: Automate tracking of M-Shwari loans and savings using the same pattern-matching intelligence used for Fuliza.
*   **Why Deferred**: Fuliza Intelligence V1 must be validated first. Daraja C2B integration is a higher priority infrastructure dependency.

---

## 📱 UX & Navigation Patterns (Deferred)

### Intelligent Back Button
*   **Status**: DEFERRED.
*   **Objective**: A lightweight "Previous Screen" pattern for deep menus.
*   **Design**: One-step historical pointer only. No complex journey graphs or session replays.
*   **Why Deferred**: Current command-based navigation (using /menu or /cancel) is sufficient for V1 stability.

---

## 📊 Credit Intelligence Evolution

### Fuliza Intelligence V1 (Current)
*   **Scope**: Access Fee burden, Usage Frequency, and Repayment Nudges.
*   **Constraint**: Deterministic logic only (no LLMs).
*   **Gating**: Advanced analytics restricted to **Pro Tier** to incentivize conversion.
