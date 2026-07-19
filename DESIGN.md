---
name: BrowserBot Design System
description: Flat, developer-first monospace and sans-serif interface for local browser tool generators
colors:
  text: "#6b6375"
  text-h: "#08060d"
  bg: "#ffffff"
  border: "#ebebeb"
  code-bg: "#f4f3ec"
  accent: "#f7f7f7"
  text-dark: "#9ca3af"
  text-h-dark: "#f3f4f6"
  bg-dark: "#16171d"
  border-dark: "#2e303a"
  code-bg-dark: "#1f2028"
  accent-purple: "#c084fc"
typography:
  display:
    fontFamily: "Geist Variable, system-ui, sans-serif"
    fontSize: "56px"
    fontWeight: 500
    lineHeight: 1
    letterSpacing: "-1.68px"
  body:
    fontFamily: "Geist Variable, system-ui, sans-serif"
    fontSize: "18px"
    lineHeight: 1.45
    letterSpacing: "0.18px"
  code:
    fontFamily: "ui-monospace, Consolas, monospace"
    fontSize: "15px"
    lineHeight: 1.35
rounded:
  sm: "6px"
  md: "8px"
  lg: "10px"
---

# Design System: BrowserBot

## 1. Overview

**Creative North Star: "The Monochromatic Lab"**

"The Monochromatic Lab" describes a precise, high-fidelity developer utility focused on text legibility, telemetry logs, and dark-mode comfort. The interface rejects generic admin dashboard layouts, overly heavy glassmorphism, or futuristic AI neon glows that reduce text readability. Instead, it relies on flat structures, strong content-driven grids, clear typographic hierarchy, and purposeful monospace elements to deliver system execution state.

Key Characteristics:
* Flat layout boundaries delimited by thin borders instead of dropshadow cards.
* High monospace contrast for code snippets and live telemetry feedback.
* Minimal accents (utilizing a single purple-accent tint color to identify interactive focus).

## 2. Colors

A flat, purely functional color palette focusing on minimal gray visual hierarchy, prioritizing dark-mode legibility for long operator sessions.

### Primary
* **Off-Black Ink** (`#08060d` in light mode, `#f3f4f6` in dark mode): Applied to all headings, labels, and interactive button text to ensure strong contrast.
* **Neutral Slate Text** (`#6b6375` in light mode, `#9ca3af` in dark mode): Applied to paragraph descriptions and non-heading text.

### Neutral Backgrounds
* **Pure Light Background** (`#ffffff`): Main light-mode canvas.
* **Dark Slate Background** (`#16171d`): Main dark-mode canvas.
* **Code Sandbox Base** (`#f4f3ec` in light mode, `#1f2028` in dark mode): Demarcates script files, action step listings, and telemetry outputs.

### Accents
* **Console Purple** (`#c084fc` in dark mode): Indicates active recording state, validation checks, and interactive step focus.

## 3. Typography

The typography scale prioritizes technical readability and code presentation, featuring a clean sans-serif base paired with monospace for data blocks.

* **Sans-Serif Font Stack**: `Geist Variable`, system-ui, sans-serif. Used for headings, paragraph prose, and general user navigation.
* **Monospace Font Stack**: `ui-monospace`, Consolas, monospace. Used for JSON action logs, code preview widgets, output paths, and telemetry outputs.
* **Display H1**: `56px` (decreases to `36px` on screens below 1024px) for prominent section titles.
* **Headline H2**: `24px` (decreases to `20px` on mobile/tablet resolutions).

## 4. Elevation

The design system relies on a flat & layered architecture. It explicitly avoids drop shadows or lifted volumetric elements.

* **Borders**: Outlines and boundaries use thin solid borders (`oklch(0.922 0 0)` in light mode, `#2e303a` in dark mode) to divide sections.
* **Tonal layering**: Monospace views, sidebar panels, and terminal zones are nested using a secondary background tint (`--code-bg` or `--accent-bg`) to define zones cleanly.

## 5. Components

Components are styled with a refined & restrained philosophy.

* **Interactive Buttons**: Styled with rounded corners (`--radius: 0.625rem`) and explicit border lines. Hover animations are quick and transition background colors with high contrast.
* **Monospace Containers**: Rendered using a distinct background block, internal padding (`4px 8px`), and a subtle border stroke.
* **Guided Steppers**: Linear step indicators styled with circular index badges, turning colored when active to maintain visual guidance.

## 6. Do's and Don'ts

* **Do** use monospace blocks for all dynamic parameter values, terminal telemetry, and configuration paths.
* **Do** ensure every interactive element supports keyboard tab focus and renders a visible outline ring.
* **Don't** add drop shadows or multi-layered card components to convey hierarchy. Use solid borders and contrasting backgrounds instead.
* **Don't** add heavy sliding or fading animations that delay page transitions or layout shifts.
