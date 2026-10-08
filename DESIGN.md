---
name: AlgoPeer
description: A calm, auditable workspace for course grading and cross-class review.
colors:
  primary: "#164E63"
  primary-hover: "#0E3F52"
  accent: "#D97706"
  canvas: "#F4F7F8"
  surface: "#FFFFFF"
  ink: "#17252D"
  muted: "#52636D"
  border: "#D5DEE2"
  success: "#18794E"
  warning: "#9A5B00"
  danger: "#B42318"
typography:
  headline:
    fontFamily: "Inter, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "1.75rem"
    fontWeight: 700
    lineHeight: 1.25
  body:
    fontFamily: "Inter, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
  label:
    fontFamily: "Inter, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 600
    lineHeight: 1.4
rounded:
  sm: "6px"
  md: "10px"
  lg: "14px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "{colors.surface}"
    rounded: "{rounded.sm}"
    padding: "10px 16px"
  input:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.sm}"
    padding: "10px 12px"
---

# Design System: AlgoPeer

## Overview

**Creative North Star: "The Grading Desk"**

AlgoPeer should resemble a carefully organized teacher's desk: the current task is obvious, source material is close at hand, and every decision leaves a trace. The interface is restrained and work-focused, with enough density for real course administration without becoming a decorative analytics wall.

**Key Characteristics:**
- Calm hierarchy and compact, readable forms.
- Explicit workflow states and blocking reasons.
- Evidence beside decisions, never hidden behind an AI score.
- Structural responsiveness rather than shrinking desktop layouts.

## Colors

Deep teal carries navigation and primary actions; amber is reserved for attention and review. Neutral surfaces keep long grading sessions comfortable.

**The One Accent Rule.** Accent color marks a decision or exception, never decoration.

## Typography

**Display Font:** Inter with Microsoft YaHei and system fallbacks
**Body Font:** Inter with Microsoft YaHei and system fallbacks

The single sans-serif family keeps Chinese and Latin UI labels consistent. Headings are firm but never oversized; body copy stays within 75 characters where it reads as prose.

## Elevation

The system is flat by default. Borders and tonal surface changes establish structure; a soft shadow appears only for menus and raised dialogs.

**The Flat-at-Rest Rule.** A grid of floating cards is prohibited; grouping must reflect workflow or data ownership.

## Components

### Buttons
- Primary actions use deep teal, compact padding, and a visible focus ring.
- Destructive actions require explicit wording and use danger color only at the decision point.

### Cards / Containers
- Surfaces use 10–14px corners, one-pixel borders, and workflow-based grouping.

### Inputs / Fields
- Inputs use persistent labels, clear help text, inline validation, and do not rely on placeholders.

### Navigation
- Desktop uses a stable left workspace rail; narrow screens collapse it into a top navigation region without hiding the current page title.

## Do's and Don'ts

### Do:
- **Do** show status text alongside color.
- **Do** place evidence, confidence, and model version beside AI suggestions.
- **Do** preserve keyboard focus and 44px touch targets for primary controls.

### Don't:
- **Don't** use decorative analytics dashboards, neon AI aesthetics, glassmorphism, or oversized vanity metrics.
- **Don't** use colored side-stripe borders or gradient text.
- **Don't** present automated analysis as a final grade.
