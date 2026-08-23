---
name: single-file-app
description: Standardized specification for generating zero-dependency, self-contained single-file HTML web applications using CDN libraries, inline CSS/JS, and LocalStorage.
---

# 📦 Single-File Application Specification Skill

This skill guides the AI agent to produce completely self-contained web applications encapsulated within a single `.html` file.

## 🎯 Architecture Standards

1. **Zero Node/NPM Prerequisites**:
   - The user must be able to double-click the `.html` file to open and run it directly in any modern web browser.
   - All external libraries must be loaded via reputable, high-speed public CDNs (e.g. `cdn.tailwindcss.com`, `cdnjs.cloudflare.com`, `unpkg.com`).

2. **Standard HTML Template Structure**:
   ```html
   <!DOCTYPE html>
   <html lang="zh-CN" class="dark">
   <head>
     <meta charset="UTF-8" />
     <meta name="viewport" content="width=device-width, initial-scale=1.0" />
     <title>Application Title</title>
     <!-- Tailwind CSS CDN -->
     <script src="https://cdn.tailwindcss.com"></script>
     <!-- Lucide Icons CDN -->
     <script src="https://unpkg.com/lucide@latest"></script>
     <!-- Canvas / Confetti / Sound CDN if needed -->
     <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.9.3/dist/confetti.browser.min.js"></script>
   </head>
   <body class="bg-slate-950 text-slate-100 min-h-screen antialiased">
     <!-- App Content -->
     <div id="app" class="max-w-4xl mx-auto px-4 py-8">
       <!-- Dynamic UI -->
     </div>

     <!-- App Logic -->
     <script>
       // State management, LocalStorage persistence, and Event Listeners
       lucide.createIcons();
     </script>
   </body>
   </html>
   ```

3. **Data Persistence**:
   - Use browser `localStorage` for state persistence (settings, history, user preferences, counters) so data survives page refreshes without requiring a backend database.
