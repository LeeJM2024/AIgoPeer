---
name: AlgoPeer
description: A calm, auditable workspace for course grading and cross-class review.
colors:
  primary: "#0F766E"
  primary-hover: "#115E59"
  accent: "#D97706"
  canvas: "#F1F4F3"
  surface: "#FFFFFF"
  ink: "#19363C"
  muted: "#526B70"
  border: "#E0E7EC"
  success: "#17734E"
  warning: "#925B0C"
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

2026-10-16 第二轮视觉重设计：以「算法课程档案夹」为概念，采用深青导航、浅色工作区、分色课程封面、算法插画和可暂停动画。登录页改为课程标签表单与插画并置，附真实演示界面的交互预览。当前规则见 [MASTER.md](design-system/algopeer/MASTER.md)，实现以 `frontend/src/workspace.css` 与组件为准。

当前视觉约定：系统中文无衬线字体；工作区正文 15px、公开页正文与表单 16px；工作区标题 30px、宣传标题最高 56px；容器圆角 6px、主要按钮 4px；无静态阴影、玻璃态或渐变。插画只表现算法结构与代码，不突出五人协作评审。公开页和工作台总览可以有宣传图，实际编程和评分操作页保持专注。

以下为历史设计记录：保留任务层次、真实状态、证据可追溯等产品原则；与本段和 MASTER 冲突的视觉约定（居中登录、白色导航、无宣传图等）已被本轮明确替代。

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
- **Do** explain review findings in plain Chinese, with score comparisons available on demand. Keep model versions, API configuration, and runtime diagnostics in administrator documentation.
- **Do** preserve keyboard focus and 44px touch targets for primary controls.

### Don't:
- **Don't** use decorative analytics dashboards, neon AI aesthetics, glassmorphism, or oversized vanity metrics.
- **Don't** use colored side-stripe borders or gradient text.
- **Don't** present automated analysis as a final grade.


## Teacher workspace refinements (2026-10-13)

- Teachers should see their assignments and next action first. Keep headings literal and remove marketing slogans and architecture explanations.
- Use a white navigation rail, quiet teal selection states, small line icons, and a light gray workspace. Group content by task, not by implementation module.
- The login page has one centered form. Class and topic creation forms open only when requested.
- Show assignment search and status filters above the list. Put the next workflow action before detailed configuration.
- Review evidence uses readable reasons and rubric score comparisons. Preserve zero values and distinguish missing values; do not display a fallback result as an available model estimate.
- Keep service configuration and API credentials out of the teacher interface. Show availability and a useful route back to coursework.

References used for task organization:
- [Google Classroom: teacher work and review status](https://support.google.com/edu/classroom/answer/9157286?hl=zh-CN)
- [Moodle: viewing and grading an assignment](https://docs.moodle.org/501/en/Viewing_an_assignment)
- [Canvas: Gradebook](https://community.instructure.com/en/kb/articles/660826-how-do-i-use-the-gradebook)
