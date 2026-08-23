---
name: tailwind-ui-master
description: Expert UI/UX design skill for crafting modern, aesthetically pleasing web interfaces using Tailwind CSS with dark mode, glassmorphism, fluid typography, and micro-interactions.
---

# 🎨 Tailwind UI Master Skill

This skill guides the AI agent to generate clean, modern, and visually stunning user interfaces using Tailwind CSS.

## 🎯 Core Principles

1. **Dark Mode First & Cyberpunk/Clean Aesthetic**:
   - Backgrounds: Use deep rich dark colors like `bg-slate-950`, `bg-zinc-900`, `bg-gray-950`.
   - Cards/Containers: Use semi-transparent dark backgrounds with glassmorphism: `bg-white/5 backdrop-blur-md border border-white/10 shadow-2xl rounded-2xl`.
   - Accents: Use vibrant gradients such as `from-indigo-500 via-purple-500 to-pink-500` or `from-emerald-400 to-cyan-500`.

2. **Typography & Hierarchy**:
   - Title: `text-2xl sm:text-4xl font-extrabold tracking-tight text-transparent bg-clip-text bg-gradient-to-r from-white via-slate-200 to-slate-400`.
   - Subtitle: `text-sm sm:text-base text-slate-400 leading-relaxed`.
   - Micro-copy/Labels: `text-xs font-semibold uppercase tracking-wider text-slate-500`.

3. **Buttons & Interactive Elements**:
   - Primary Action: `px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-medium shadow-lg shadow-indigo-500/25 hover:shadow-indigo-500/40 hover:scale-[1.02] active:scale-[0.98] transition-all duration-200 cursor-pointer`.
   - Ghost/Secondary: `px-4 py-2 rounded-xl bg-white/5 hover:bg-white/10 text-slate-300 border border-white/10 hover:border-white/20 transition-all duration-200 cursor-pointer`.

4. **Responsive Layouts**:
   - Always include mobile-first classes (`flex-col sm:flex-row`, `grid-cols-1 sm:grid-cols-2 lg:grid-cols-3`).
   - Use container constraints: `max-w-4xl mx-auto px-4 py-8`.
