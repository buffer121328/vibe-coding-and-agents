---
name: agent-browser
description: Automated headless browser control and testing skill for opening local HTML pages, simulating user clicks/inputs, taking screenshots, and verifying visual and interactive functionality.
---

# 🌐 Agent Browser Skill

This skill equips the AI agent with automated browser capabilities to test, inspect, and verify web applications.

## 🎯 Capabilities

1. **Page Loading & Rendering**:
   - Open local `.html` files or development server URLs (e.g. `http://localhost:3000` or `file:///path/to/index.html`).
   - Wait for DOM readiness and animation frames to complete before taking action.

2. **User Interaction Simulation**:
   - Click buttons, tabs, dropdowns, and interactive elements.
   - Enter text into input fields, textareas, and search boxes.
   - Trigger keyboard shortcuts and mouse hover states.

3. **Visual Inspection & Verification**:
   - Capture full-page or element-specific screenshots to verify visual layout and styling.
   - Check browser console logs for JavaScript errors, unhandled rejections, or missing CDN resources.
   - Report visual regressions or broken layout components back to the agent for self-healing.
