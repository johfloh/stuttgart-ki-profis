# DESIGN.md — Handwerker KI Landing Page

## 1. Brand Strategy & Voice

### Brand Essence
Handwerker KI is a B2B Micro-SaaS for German trade professionals (Handwerksbetriebe).
It transforms WhatsApp voice messages into professional PDF quotes — using price list matching,
not AI guesswork.

### Brand Personality
- **Reliable** — "Macht was es verspricht." No hype, no fluff.
- **Local** — Speaks the language of the Werkstatt, not Silicon Valley.
- **Direct** — Short sentences, clear value, no bullshit.
- **Modern but grounded** — Tech-forward without being intimidating.

### Voice Guidelines
| Dimension | Approach |
|-----------|----------|
| Tone | Professional but warm. Like a trusted Meister who also happens to be a tech nerd. |
| Register | "Sie" (formal). Respectful without being stiff. |
| Sentence length | Short. 12–18 words average. |
| Jargon | Zero. No "disrupt", "scalable", "synergy". Handwerker terms only. |
| Emotional target | Relief + confidence. "Endlich kehrt Ruhe ein." |
| Cultural note | German Handwerker are proud of their craft. Never imply software replaces skill. It *helps*. |

### Tagline (Primary)
**"KI fürs Handwerk. Angebote in Minuten."**

### Tagline (Secondary / Hero)
**"Aus Sprachnachricht wird Angebot. In Sekunden."**

---

## 2. Color Palette

### Semantic Token Mapping

```yaml
colors:
  # PRIMARY — Trust, stability, German engineering feel
  brand-900: "#0F1923"   # Deepest navy — hero backgrounds, footers
  brand-800: "#1A2332"   # Dark navy — cards, sections
  brand-700: "#2B4C7E"   # Primary blue — CTAs, links, active states
  brand-600: "#3B6CB7"   # Hover states, secondary CTA

  # ACCENT — Energy, action, construction orange
  accent-600: "#E3540B"  # Primary accent — key CTAs, highlights
  accent-500: "#F0651E"  # Hover state for accent
  accent-400: "#FF8C42"  # Warm secondary — badges, subtle highlights

  # NEUTRAL — Clean, warm, approachable
  neutral-50:  "#F8F6F3"  # Off-white background (warmth)
  neutral-100: "#F0EDE8"  # Section alt backgrounds
  neutral-200: "#E5E0D8"  # Borders, dividers
  neutral-400: "#9CA3AF"  # Muted text
  neutral-600: "#4B5563"  # Body text (secondary)
  neutral-800: "#1F2937"  # Body text (primary)
  neutral-900: "#111827"  # Headings

  # SEMANTIC
  surface:     "#FFFFFF"  # Card & modal surfaces
  success:     "#059669"  # Positive signals, checkmarks
  warning:     "#D97706"  # Caution
  error:       "#DC2626"  # Error states
```

### Color Psychology Rationale
- **Brand Blue (#1A2332 → #2B4C7E):** Deep navy conveys stability, expertise, and trust.
  German Handwerker associate blue with quality (Bosch, Siemens, Mercedes).
- **Safety Orange (#E3540B):** Construction zone colours trigger recognition and urgency.
  High contrast against blue — excellent for CTA buttons.
- **Warm Off-White (#F8F6F3):** Avoids the cold "tech startup" look. Feels like
  a real workshop, not a sterile software company.

---

## 3. Typography

### Primary Font: Inter
- **Why:** Excellent German character support (Umlauts, ß), highly readable at all sizes,
  open-source, loads fast via Google Fonts.
- **Weights used:** 400 (body), 500 (strong body), 600 (subheadings), 700 (headings), 800 (hero)

### Fallback Stack
```css
font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
```

### Type Scale
```yaml
type-scale:
  hero-heading:  [3.5rem, 2.5rem]  # Desktop / Mobile
  section-heading: [2.25rem, 1.75rem]
  subheading:   [1.25rem, 1.125rem]
  body:         [1rem, 0.95rem]
  small:        [0.875rem, 0.875rem]
  caption:      [0.75rem, 0.75rem]
  button:       [0.95rem, 0.9rem]   # Semibold
```

---

## 4. Spacing & Layout

```yaml
spacing:
  section-padding: [6rem, 3rem]        # Desktop / Mobile
  container-max:   "1200px"
  grid-gap:        [2rem, 1.25rem]
  card-padding:    [2rem, 1.5rem]
  cta-sticky-height: "80px"

breakpoints:
  sm:  "640px"
  md:  "768px"
  lg:  "1024px"
  xl:  "1280px"
```

---

## 5. Component Design

### Buttons
| Type | BG | Text | Hover | Border Radius |
|------|----|------|-------|---------------|
| Primary CTA | accent-600 | White | accent-500 | 8px |
| Secondary CTA | brand-700 | White | brand-600 | 8px |
| Ghost | transparent | brand-700 | bg-brand-50 | 8px |
| Outline | transparent | brand-700 | bg-brand-50 + border | 8px |

### Cards
- Background: White (`#FFFFFF`)
- Border: 1px solid `neutral-200`
- Border-radius: 12px
- Shadow: `0 1px 3px rgba(0,0,0,0.06), 0 1px 2px rgba(0,0,0,0.04)`
- Hover shadow: `0 10px 25px rgba(0,0,0,0.08)`

### Form Inputs
- Height: 48px (touch-friendly)
- Border: 2px solid `neutral-200`
- Focus: 2px solid `brand-700`
- Border-radius: 8px

### Navigation
- Sticky top bar (blur glass effect)
- Desktop: horizontal links + CTA button
- Mobile: hamburger menu with slide-in drawer

---

## 6. Page Structure

```
┌─────────────────────────────────────────────┐
│ NAVBAR (sticky, glassmorphism)               │
│ Logo · Features · Preise · Kontakt · [CTA]   │
├─────────────────────────────────────────────┤
│ HERO                                         │
│ Headline + Subline + Primary CTA             │
│ Mockup / Hero image                          │
├─────────────────────────────────────────────┤
│ TRUST BAR (Logo cloud / Awards / Numbers)    │
│ "Bereits X Angebote erstellt"                │
├─────────────────────────────────────────────┤
│ FEATURES (3-column grid)                     │
│ 🎤 Sprachnachricht → Angebot                 │
│ 📊 Preislisten-Matching                      │
│ 📄 PDF in Sekunden                           │
│ 💬 Automatische Kundenantwort                │
│ ⏱ Zeiterfassung                             │
├─────────────────────────────────────────────┤
│ HOW IT WORKS (3-step)                        │
│ 1. WhatsApp Sprachnachricht                  │
│ 2. KI parst + matched Preise                 │
│ 3. PDF Angebot an Kunden                     │
├─────────────────────────────────────────────┤
│ SOCIAL PROOF (Testimonials)                  │
│ 2-3 Handwerker Stimmen                       │
│ "Endlich weniger Bürokratie"                 │
├─────────────────────────────────────────────┤
│ PRICING (3 tiers)                            │
│ Basis 19€ · Pro 39€ · Enterprise 79€         │
├─────────────────────────────────────────────┤
│ CONTACT / STICKY CTA BAR                     │
│ "Jetzt kostenlos testen"                     │
│ Name · Betrieb · WhatsApp · Submit           │
├─────────────────────────────────────────────┤
│ FOOTER                                       │
│ Impressum · Datenschutz · AGB                │
└─────────────────────────────────────────────┘
```

---

## 7. SEO & Metadata

### Target Keywords (German)
- Ki für Handwerker
- Angebot erstellen Handwerk
- WhatsApp Angebot Vorlage
- KI Angebotsassistent
- Handwerker Software
- Angebot Schreiben Handwerk
- Angebotssoftware Kleinbetrieb
- Rechnung Schreiben Handwerk
- Digitale Angebotssoftware

### Page Metadata
```yaml
title: "Handwerker KI — KI fürs Handwerk. Angebote in Minuten."
description: "WhatsApp Sprachnachricht rein, professionelles PDF Angebot raus.
  KI-gestützter Angebotsassistent speziell für deutsche Handwerksbetriebe.
  Inklusive Preislisten-Matching, Zeiterfassung und automatischer Kundenkommunikation."
og:
  title: "Handwerker KI — Angebote in Minuten"
  description: "Aus WhatsApp Sprachnachricht wird in Sekunden ein professionelles PDF-Angebot."
  type: website
  locale: de_DE

schema:
  type: SoftwareApplication
  applicationCategory: BusinessApplication
  operatingSystem: Web
  offers:
    price: 19
    priceCurrency: EUR
  author:
    type: Organization
    name: Handwerker KI
    address: Stuttgart, Germany
```

---

## 8. Iconography

- Use **Feather Icons** (open-source, clean, consistent stroke-width)
- Feature icons: Mic, FileText, Clock, MessageCircle, CheckCircle, Zap
- Social proof: quote marks as SVG decorations
- All icons must be inline SVG for performance (no icon font library)

---

## 9. Performance Targets

```yaml
performance:
  lighthouse-desktop: 95+
  lighthouse-mobile:  90+
  first-meaningful-paint: "<1.5s"
  total-page-weight: "<300KB"
  google-fonts: "1 request (Inter 400,500,600,700)"
```

---

## 10. Accessibility

- All interactive elements keyboard-navigable
- ARIA labels on icon-only buttons
- Focus-visible outlines (not :focus)
- Color contrast ratio > 4.5:1 for body text
- Skip-to-content link
- Semantic HTML landmarks (header, main, section, footer, nav)