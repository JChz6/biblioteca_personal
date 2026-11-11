---
name: Biblioteca Personal
description: Japanese-vintage library — cream ink, slate blue and orange on near-black
colors:
  bg: "#1b1a19"
  surface: "#252422"
  surface-hover: "#2e2c29"
  text: "#e8d8c9"
  text-muted: "#ab9f93"
  border: "#3e3b37"
  accent: "#f3701e"
  accent-hover: "#ff8a3d"
  accent-deep: "#3d2414"
  blue: "#4b607f"
  blue-soft: "#9db0cd"
  blue-deep: "#273140"
typography:
  display:
    fontFamily: "Libre Caslon Text, Georgia, serif"
    fontSize: "clamp(2.5rem,5vw,4rem)"
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: "-.025em"
  title:
    fontFamily: "Libre Caslon Text, Georgia, serif"
    fontSize: "20px"
    fontWeight: 700
    lineHeight: 1.2
  body:
    fontFamily: "DM Sans, system-ui, sans-serif"
    fontSize: "16px"
    lineHeight: 1.5
  label:
    fontFamily: "DM Sans, system-ui, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    letterSpacing: ".16em"
  note:
    fontFamily: "Caveat, cursive"
    fontSize: "30px"
    lineHeight: 1.05
rounded:
  control: "8px"
  card: "12px"
  pagination: "7px"
spacing:
  small: "8px"
  medium: "16px"
  large: "24px"
  section: "32px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.bg}"
    rounded: "{rounded.control}"
    padding: "10px 20px"
  button-format:
    textColor: "{colors.accent}"
    rounded: "{rounded.control}"
    padding: "9px 16px"
  button-ghost:
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "10px 20px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.control}"
    padding: "11px 14px"
---

# Design System: Biblioteca Personal

## Overview

**Creative North Star: "La biblioteca editorial"**

A charcoal library with warm offwhite text and orange actions. Editorial serif headings give the collection weight; sans-serif controls keep browsing direct, and a handwritten contribution note adds a personal invitation.

This document records the approved implementation in `app/static/style.css`, `app/static/app.js`, and the base and catalog templates. The north-star label is descriptive shorthand for that established direction.

**Key Characteristics:**
- Horizontal desktop navigation with a compact mobile menu.
- Serif book titles in divided rows, with native filters and visible format actions.
- Restrained orange emphasis and a handwritten upload invitation.

## Colors

Japanese/American vintage palette (cream `#e8d8c9`, slate blue `#4b607f`, orange `#f3701e` on near-black). Orange (`accent`) is reserved for action: upload button, format links, current page, active nav underline, selection and focus; `accent-deep` is its tonal hover. Cream (`text`) is the primary ink. Slate blue is the secondary hue for wayfinding and identity: document tiles (`blue-deep` at rest, `blue` on row hover), account initial, author letter headings and the contribution note (`blue-soft`), alphabet-index hover, info banners and neutral badges. Raw `blue` is never used as text on the dark ground (2.7:1); use `blue-soft`. The header closes with a one-pixel border (a tri-colour stripe was tried and rejected by the user). Success (sage) and pending (orange on `accent-deep`) keep their semantic tints. Verified contrast: cream/bg 12.5, muted/bg 6.7, orange/bg 5.9, bg/orange 5.9, cream/blue 4.6, blue-soft/blue-deep 6.0.

## Typography

Libre Caslon Text gives the hero and book titles their editorial character. DM Sans handles navigation, body copy and controls. Caveat is reserved for the contribution note and its drawn arrow. Fonts load through Google Fonts with local fallbacks in the CSS.

The mobile hero is 44px (40px at 360px and below), mobile book titles are 18px, and the handwritten note becomes 22px. Secondary page headings use 44px on desktop and 36px on mobile. The uppercase collection label is a label treatment, not a change to the underlying copy.

## Layout

Header and content share a centered 1536px maximum width and desktop horizontal padding of `clamp(24px,4.4vw,72px)`. Main content has 44px top padding. The desktop catalog uses three columns: flexible title/author, category, formats; rows have 24px gaps and 18px vertical padding.

At 760px and below, content uses 22px side padding, navigation expands from a menu button, filters expand vertically, and each book becomes a two-column row with category under identity and formats at the right. At 360px and below, side padding drops to 16px and document icons disappear. Between 761px and 1200px, the contribution note stacks below its action. Pagination wraps, retaining 44px-high targets.

Authors and categories use single-column directories, capped at 960px. Authors have letter groups with 28px orange serif headings and a wrapping index of 44px controls; categories use a simple alphabetical list. Rows are fully clickable, with the name left and count right, at least 60px high and padded 18px 12px. Mobile rows remove horizontal padding and reduce the gap to 16px. Spanish ordering ignores accents while retaining Ñ after N.

## Elevation & Depth

The system is flat: no box-shadow vocabulary. Tonal surfaces, one-pixel borders and row dividers express hierarchy. The image dialog uses an `rgba(0,0,0,.88)` backdrop; it is the strongest depth treatment.

## Shapes

Controls use 10px corners; popovers, pending cards and table cards use an 18px curve echoing the palette's rounded color blocks. Catalog entries remain divided rows rather than enclosed cards. Circular account initials are confined to the header.

## Components

- **Buttons:** orange filled upload action; orange outlined format actions; neutral outlined secondary actions. Buttons have at least 44px height, with a 52px desktop primary action. Focus is a 2px orange outline offset by 4px. Disabled buttons reduce opacity to .5.
- **Search and filters:** a broad surface-colored search field precedes native select controls. Search focus changes the containing border to orange; select changes submit the current GET form. Mobile filters use an expanded-state toggle.
- **Navigation:** desktop links use a thin orange active underline; mobile active links use a charcoal surface and orange text. The sticky header hides on downward scrolling, returns on upward scrolling, and stays visible for focus or open menus. Its transform transition is 220ms with `cubic-bezier(.16,1,.3,1)`; reduced-motion mode removes transitions.
- **Collection row:** serif title, muted author and category, a small document mark, and outlined download-format actions. Hover adds a tonal surface and orange document detail. Status badges use compact filled chips on supporting pages.
- **Directories:** shared divided rows gain a surface background and orange name on hover. Author search ignores case and accents, hides empty letter groups and their index links, and announces matching counts or an explicit no-results message. Category names link directly to the filtered catalog.
- **Contribution invitation:** preserve the handwritten “También puedes contribuir” note and curved arrow adjacent to “Subir archivo”, including its responsive direction.
- **Godzilla dialog:** a small light-gray “¿Godzilla?” trigger opens the complete supplied meme. The image uses contain sizing inside the viewport; body scroll is locked. Escape, backdrop and close button dismiss it; closing restores the previous scroll position and trigger focus.
- **Asset provenance:** `app/static/library-icon.jpg` is a byte copy of the user-supplied `app/icon/icon-master-01.jpg`. `app/static/godzilla.png` is a byte copy of the user-supplied meme from `/var/folders/my/kp0ljbs11vb8dwtswcszk3sr0000gn/T/codex-clipboard-3wX7Vv.png`. Preserve these originals rather than redrawing them.

## Do's and Don'ts

- Do preserve “Colección completa”, “Sé como Godzilla.” and “También puedes contribuir”.
- Do retain native select controls, visible focus, accessible names and reduced-motion support.
- Do show the full Godzilla image within the viewport and restore focus and page position after closing.
- Don't substitute generated artwork for the supplied library icon or Godzilla meme.
- Don't crop the meme or allow the open dialog or background to scroll.
- Don't hide a header that contains keyboard focus or an open menu.

Icon margin refinement: `app/static/library-icon.svg` embeds the original JPEG unchanged and crops its exterior white margin with a rounded clip. The header and favicon use this wrapper. Generated alternatives were discarded.
