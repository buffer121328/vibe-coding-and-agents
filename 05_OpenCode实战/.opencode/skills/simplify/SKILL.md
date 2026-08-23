---
name: simplify
description: Code refinement and dead-code elimination skill for refactoring complex logic, removing redundant boilerplate, and making single-file code exceptionally clean, readable, and performant.
---

# 🧹 Simplify Code Refactoring Skill

This skill instructs the AI agent to critically review generated code, eliminate cognitive overhead, remove redundant boilerplate, and ensure code purity.

## 🎯 Refactoring Rules

1. **Eliminate Deep Nesting**:
   - Prefer early returns over deeply nested `if-else` blocks.
   - Replace long procedural ladders with clear lookup maps or pure transformation pipelines.

2. **Remove Unused & Dead Code**:
   - Strip out debug `console.log` statements, unused variable declarations, and obsolete helper functions.
   - Consolidate duplicated styling classes into reusable utility components or loops.

3. **Clarity & Pedagogical Elegance**:
   - Ensure variables and functions are named intuitively (e.g. `incrementCounter` instead of `inc`).
   - Add concise, high-value comments explaining non-obvious algorithms or browser API quirks to facilitate beginner learning.
