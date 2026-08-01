{
  "product": {
    "name": "Sentry RAG",
    "visual_personality": [
      "technical",
      "secure",
      "control-room",
      "precise",
      "audit-ready",
      "low-glare dark UI",
      "subtle neon instrumentation"
    ],
    "north_star": "Make access control feel provable: retrieval is filtered by role before the model sees content; every answer is grounded with citations + a designed retrieval-detail panel."
  },
  "global_rules": {
    "theme": "dark-only",
    "no_purple_for_ai": true,
    "gradient_restriction": {
      "max_viewport_coverage": "20%",
      "prohibited_examples": [
        "from-blue-500 to-purple-600",
        "from-purple-500 to-pink-500",
        "from-green-500 to-blue-500",
        "from-red-500 to-pink-500"
      ],
      "allowed_usage": [
        "hero background only (decorative)",
        "section background accents only",
        "large CTA surfaces only (subtle)"
      ]
    },
    "testing": {
      "data_testid_required": "All interactive and key informational elements MUST include data-testid in kebab-case describing role, not appearance."
    }
  },
  "design_tokens": {
    "css_custom_properties": {
      "notes": "Implement by overriding shadcn tokens in frontend/src/index.css under .dark. Keep base near deep navy/charcoal (not pure black) for legibility.",
      "colors": {
        "--background": "215 28% 7%  /* #0B1220 deep navy */",
        "--foreground": "210 20% 96%  /* #F1F5F9 */",
        "--card": "215 26% 9%  /* #0F172A */",
        "--card-foreground": "210 20% 96%",
        "--popover": "215 26% 9%",
        "--popover-foreground": "210 20% 96%",
        "--primary": "186 92% 45%  /* cyan-teal accent #06B6D4-ish */",
        "--primary-foreground": "215 28% 7%",
        "--secondary": "215 20% 14%  /* #162033 */",
        "--secondary-foreground": "210 20% 96%",
        "--muted": "215 18% 16%",
        "--muted-foreground": "215 12% 70%  /* #A7B0C0 */",
        "--accent": "215 20% 14%",
        "--accent-foreground": "210 20% 96%",
        "--border": "215 18% 18%  /* #1F2A3D */",
        "--input": "215 18% 18%",
        "--ring": "186 92% 45%",
        "--destructive": "0 72% 52%  /* #EF4444 */",
        "--destructive-foreground": "210 20% 96%",
        "semantic": {
          "allowed": "158 78% 42%  /* #22C55E-ish but slightly cooler */",
          "blocked": "0 72% 52%",
          "pending": "38 92% 50%  /* amber #F59E0B */",
          "info": "199 89% 48%  /* sky #0EA5E9 */"
        },
        "surfaces": {
          "surface_0": "#0B1220",
          "surface_1": "#0F172A",
          "surface_2": "#111C33",
          "surface_3": "#162033"
        },
        "glow": {
          "glow_cyan": "rgba(34, 211, 238, 0.18)",
          "glow_green": "rgba(34, 197, 94, 0.16)",
          "glow_red": "rgba(239, 68, 68, 0.14)"
        }
      },
      "radius": {
        "--radius": "0.75rem",
        "radius_sm": "0.5rem",
        "radius_md": "0.75rem",
        "radius_lg": "1rem"
      },
      "shadows": {
        "shadow_panel": "0 0 0 1px rgba(148,163,184,0.10), 0 12px 30px rgba(0,0,0,0.45)",
        "shadow_glow": "0 0 0 1px rgba(34,211,238,0.18), 0 0 24px rgba(34,211,238,0.12)"
      },
      "typography": {
        "font_pairing": {
          "display": "Space Grotesk (Google Fonts)",
          "body": "Inter (Google Fonts)",
          "mono": "IBM Plex Mono (Google Fonts)"
        },
        "scale": {
          "h1": "text-4xl sm:text-5xl lg:text-6xl",
          "h2": "text-base md:text-lg",
          "body": "text-sm md:text-base",
          "small": "text-xs"
        },
        "tracking": {
          "display": "tracking-[-0.02em]",
          "mono": "tracking-[0.08em] uppercase"
        }
      },
      "spacing": {
        "layout": {
          "page_padding": "px-4 sm:px-6 lg:px-8",
          "section_padding": "py-14 sm:py-18 lg:py-24",
          "stack_gap": "gap-6 sm:gap-8"
        }
      }
    },
    "tailwind_usage_notes": [
      "Prefer bg-[hsl(var(--background))] etc via shadcn tokens.",
      "Use subtle borders: border-white/10 or border-[hsl(var(--border))].",
      "Avoid pure black (#000) large areas; use deep navy surfaces for readability.",
      "No transition:all; use transition-colors, transition-opacity, transition-shadow."
    ]
  },
  "texture_and_background": {
    "control_room_layers": {
      "base": "Solid deep navy background.",
      "grid": "Add a faint grid using CSS repeating-linear-gradient at 24px spacing; opacity 0.06–0.10.",
      "scanlines": "Optional scanline overlay (1px line every 6px) at opacity 0.04–0.06.",
      "noise": "Add subtle noise overlay (CSS mask or background-image) at opacity 0.05–0.08."
    },
    "css_snippets": {
      "app_shell_bg": ".app-shell { background-color: hsl(var(--background)); background-image: radial-gradient(800px 400px at 20% 10%, rgba(34,211,238,0.10), transparent 60%), radial-gradient(700px 380px at 80% 20%, rgba(34,197,94,0.08), transparent 55%), repeating-linear-gradient(0deg, rgba(148,163,184,0.06) 0px, rgba(148,163,184,0.06) 1px, transparent 1px, transparent 6px), repeating-linear-gradient(90deg, rgba(148,163,184,0.05) 0px, rgba(148,163,184,0.05) 1px, transparent 1px, transparent 24px); }",
      "panel_surface": ".panel { background: rgba(15,23,42,0.72); backdrop-filter: blur(10px); border: 1px solid rgba(148,163,184,0.14); box-shadow: 0 12px 30px rgba(0,0,0,0.45); }"
    },
    "gradient_policy_note": "Keep decorative radial gradients confined to hero header area only (<=20% viewport). For the rest, rely on solid surfaces + grid/scanline textures."
  },
  "typography": {
    "fonts": {
      "google_fonts_import": "In public/index.html add: https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Space+Grotesk:wght@500;600;700&family=IBM+Plex+Mono:wght@400;500;600&display=swap",
      "usage": {
        "brand_wordmark": "Space Grotesk 700",
        "headings": "Space Grotesk 600",
        "body": "Inter 400/500",
        "mono_labels": "IBM Plex Mono 500 (for role badges, timestamps, retrieval stats)"
      }
    },
    "content_rules": [
      "Assistant answers: max-w-prose for readability; increase line-height (leading-7).",
      "Use monospace only for metadata (role, chunk counts, doc ids), not for long paragraphs.",
      "Use subtle letterspacing for control-room labels: tracking-[0.12em] uppercase text-xs."
    ]
  },
  "iconography": {
    "library": "lucide-react",
    "style": [
      "Use 1.5px stroke icons",
      "Prefer geometric/technical icons: Shield, Lock, FileText, Database, Search, Radar, Activity, Users, KeyRound, Upload, CheckCircle2, XCircle, Clock, BookOpen"
    ],
    "usage_rules": [
      "Icons are accents; keep them muted (text-slate-300) until hover/active.",
      "Never use emoji icons."
    ]
  },
  "motion": {
    "principles": [
      "Purposeful, instrument-like motion (no bouncy easing).",
      "Use short fades + slight translate for entrances.",
      "Use glow intensification on hover for primary actions.",
      "Respect prefers-reduced-motion: disable parallax/particles and reduce durations."
    ],
    "framer_motion_presets": {
      "ease": "[0.16, 1, 0.3, 1]",
      "durations": {
        "fast": 0.12,
        "base": 0.18,
        "slow": 0.28
      },
      "variants": {
        "fadeUp": "{ hidden: { opacity: 0, y: 10 }, show: { opacity: 1, y: 0 } }",
        "panelIn": "{ hidden: { opacity: 0, scale: 0.98 }, show: { opacity: 1, scale: 1 } }"
      }
    },
    "micro_interactions": {
      "buttons": "hover: shadow + subtle glow; active: scale-[0.98]",
      "sidebar_items": "hover: bg-white/5; active: border-l-cyan + glow dot",
      "citation_chips": "hover: border-cyan/40 + bg-cyan/10",
      "retrieval_panel": "collapsible with height animation + opacity fade"
    }
  },
  "components": {
    "component_path": {
      "shadcn": {
        "Button": "frontend/src/components/ui/button.jsx",
        "Input": "frontend/src/components/ui/input.jsx",
        "Textarea": "frontend/src/components/ui/textarea.jsx",
        "Card": "frontend/src/components/ui/card.jsx",
        "Badge": "frontend/src/components/ui/badge.jsx",
        "Tabs": "frontend/src/components/ui/tabs.jsx",
        "Table": "frontend/src/components/ui/table.jsx",
        "Dialog": "frontend/src/components/ui/dialog.jsx",
        "Sheet": "frontend/src/components/ui/sheet.jsx",
        "Select": "frontend/src/components/ui/select.jsx",
        "Checkbox": "frontend/src/components/ui/checkbox.jsx",
        "ScrollArea": "frontend/src/components/ui/scroll-area.jsx",
        "Separator": "frontend/src/components/ui/separator.jsx",
        "Collapsible": "frontend/src/components/ui/collapsible.jsx",
        "Tooltip": "frontend/src/components/ui/tooltip.jsx",
        "Sonner": "frontend/src/components/ui/sonner.jsx"
      }
    },
    "patterns": {
      "buttons": {
        "primary": {
          "look": "Cyan-teal solid with subtle outer glow; rounded-md; high contrast.",
          "tailwind": "bg-[hsl(var(--primary))] text-[hsl(var(--primary-foreground))] shadow-[0_0_0_1px_rgba(34,211,238,0.25),0_10px_24px_rgba(0,0,0,0.35)] hover:shadow-[0_0_0_1px_rgba(34,211,238,0.35),0_0_24px_rgba(34,211,238,0.18)] active:scale-[0.98] transition-shadow transition-colors",
          "data_testid_examples": [
            "landing-hero-primary-cta-button",
            "chat-send-button",
            "admin-approve-user-button"
          ]
        },
        "secondary": {
          "look": "Tonal dark surface with border; becomes brighter on hover.",
          "tailwind": "bg-white/0 border border-white/15 text-slate-100 hover:bg-white/5 hover:border-white/25 transition-colors",
          "data_testid_examples": [
            "landing-hero-secondary-cta-button",
            "chat-new-conversation-button"
          ]
        },
        "ghost": {
          "look": "Text button for utility actions; underline on hover.",
          "tailwind": "bg-transparent text-slate-200 hover:text-white hover:bg-white/5 transition-colors"
        }
      },
      "form_fields": {
        "input": {
          "look": "Inset dark field with subtle inner shadow; cyan ring on focus.",
          "tailwind": "bg-[rgba(15,23,42,0.6)] border-white/15 placeholder:text-slate-500 focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] focus-visible:ring-offset-0"
        },
        "error": {
          "look": "Red border + helper text; no shaking animations.",
          "tailwind": "border-red-500/40 focus-visible:ring-red-500/40"
        }
      },
      "cards_panels": {
        "panel": {
          "look": "Frosted control-room panel with grid hint; 1px border; deep shadow.",
          "tailwind": "rounded-xl border border-white/10 bg-[rgba(15,23,42,0.72)] backdrop-blur-md shadow-[0_12px_30px_rgba(0,0,0,0.45)]"
        },
        "panel_header": {
          "look": "Mono label + right-aligned status chip.",
          "tailwind": "flex items-center justify-between gap-3 border-b border-white/10 px-4 py-3"
        }
      },
      "role_badges": {
        "look": "Monospace capsule with subtle border; color-coded dot.",
        "variants": {
          "employee": "bg-slate-900/40 border-white/10 text-slate-200",
          "manager": "bg-sky-950/40 border-sky-400/20 text-sky-200",
          "hr": "bg-emerald-950/35 border-emerald-400/20 text-emerald-200",
          "admin": "bg-cyan-950/35 border-cyan-400/25 text-cyan-200"
        },
        "tailwind": "inline-flex items-center gap-2 rounded-full border px-2.5 py-1 text-xs font-medium font-mono tracking-[0.08em] uppercase"
      },
      "sidebar_item": {
        "look": "Compact row with title + timestamp; active state uses left accent bar + glow dot.",
        "tailwind": "group relative flex w-full items-start gap-3 rounded-lg px-3 py-2 text-left hover:bg-white/5 transition-colors",
        "active": "bg-white/6 border border-cyan-400/20 shadow-[0_0_0_1px_rgba(34,211,238,0.18),0_0_18px_rgba(34,211,238,0.10)]"
      },
      "message_bubbles": {
        "user": {
          "look": "Right-aligned, slightly brighter surface.",
          "tailwind": "ml-auto max-w-[92%] sm:max-w-[78%] rounded-2xl border border-white/10 bg-white/5 px-4 py-3"
        },
        "assistant": {
          "look": "Left-aligned panel with subtle glow edge.",
          "tailwind": "mr-auto max-w-[92%] sm:max-w-[78%] rounded-2xl border border-white/10 bg-[rgba(15,23,42,0.72)] px-4 py-3 shadow-[0_0_0_1px_rgba(148,163,184,0.08)]"
        },
        "meta": {
          "tailwind": "mt-2 flex flex-wrap items-center gap-2 text-xs text-slate-400"
        }
      },
      "citation_chip": {
        "look": "Small pill with doc title + section; clickable; highlights excerpt in panel.",
        "tailwind": "inline-flex items-center gap-2 rounded-full border border-white/12 bg-white/0 px-2.5 py-1 text-xs text-slate-200 hover:bg-cyan-500/10 hover:border-cyan-400/25 transition-colors",
        "data_testid_examples": [
          "chat-message-citation-chip",
          "chat-citations-panel-source-row"
        ]
      },
      "retrieval_detail_panel": {
        "signature": true,
        "look": "Collapsible instrument panel under each assistant message: shows Retrieved vs Blocked counts, plus a compact list of sources with role gating hints.",
        "structure": [
          "Header row: 'Retrieval details' + retrieved_count badge + blocked_count badge + chevron",
          "Body: two columns on desktop (Retrieved list / Blocked summary), single column on mobile",
          "Each row: doc title, chunk id, reason (blocked: role mismatch), optional score"
        ],
        "tailwind": {
          "wrapper": "mt-3 rounded-xl border border-white/10 bg-black/20",
          "header": "flex items-center justify-between gap-3 px-3 py-2",
          "badges": {
            "retrieved": "bg-emerald-500/10 text-emerald-200 border-emerald-400/20",
            "blocked": "bg-red-500/10 text-red-200 border-red-400/20"
          },
          "body": "grid gap-3 px-3 pb-3 sm:grid-cols-2"
        },
        "data_testid_examples": [
          "chat-message-retrieval-details-toggle",
          "chat-message-retrieved-count",
          "chat-message-blocked-count"
        ]
      },
      "upload_dropzone": {
        "look": "Dashed border panel with subtle animated scanline on drag-over.",
        "tailwind": "rounded-xl border border-dashed border-white/20 bg-white/0 px-4 py-6 hover:bg-white/5 transition-colors",
        "drag_over": "border-cyan-400/40 bg-cyan-500/5 shadow-[0_0_0_1px_rgba(34,211,238,0.18),0_0_18px_rgba(34,211,238,0.10)]",
        "role_checkboxes": "Use shadcn Checkbox + Label in a 2x2 grid; each option shows a colored dot + role name in mono.",
        "data_testid_examples": [
          "admin-doc-upload-dropzone",
          "admin-doc-allowed-roles-checkbox"
        ]
      },
      "pending_user_row": {
        "look": "Table row with user email, requested_at, role Select, Approve button.",
        "interaction": "Role select defaults to employee; Approve is one click; show toast on success/failure.",
        "data_testid_examples": [
          "admin-pending-user-row",
          "admin-pending-user-role-select",
          "admin-pending-user-approve-button"
        ]
      },
      "toasts": {
        "library": "sonner",
        "use_cases": [
          "rate limit hit (40 req/min)",
          "upload success/failure",
          "approval success/failure",
          "auth errors"
        ],
        "tone": "Short, operator-friendly. Include error codes when available."
      }
    }
  },
  "page_layouts": {
    "landing": {
      "layout": "Z-pattern hero then 4 feature panels in a bento grid; final CTA.",
      "hero": {
        "structure": [
          "Top nav: wordmark left, 'Skip to console' right",
          "Hero left: H1 + subheading + CTAs",
          "Hero right: 'Live retrieval' mock panel (citations + retrieved/blocked counters)"
        ],
        "cta": {
          "primary": "See how it works (scroll to features)",
          "secondary": "Skip to console (/login)"
        },
        "decor": "Particle field or subtle radar sweep behind hero only (<=20% viewport)."
      },
      "features": [
        {
          "title": "Grounded answers",
          "content": "Show example prompt + assistant answer with 2–3 citation chips."
        },
        {
          "title": "Access control at retrieval",
          "content": "Diagram-like panel: Query → Role filter → Vector search → LLM."
        },
        {
          "title": "Admin-managed knowledge base",
          "content": "Upload + role tags preview."
        },
        {
          "title": "Full audit log",
          "content": "Timeline list with role + doc ids + retrieved/blocked counts."
        }
      ],
      "final_cta": "Single decisive panel: 'Deploy provable RAG' + button to Register."
    },
    "auth_pages": {
      "layout": "Centered panel but page content left-aligned inside; background grid/scanlines.",
      "login": "Email + password + submit; link to register.",
      "register": "Email + password + confirm; submit; on success route to /pending.",
      "pending": "Status panel with Clock icon, explanation, and 'Back to login' button.",
      "change_password": "Forced flow: old password + new password + confirm; show strength hints; success toast then redirect."
    },
    "chat": {
      "desktop_layout": "3 regions: left sidebar (conversations), center chat stream, optional right drawer/panel for citations (or inline under messages).",
      "mobile_layout": "Sidebar becomes Sheet; top bar shows wordmark + role badge + menu.",
      "top_bar": [
        "User name + role badge always visible",
        "Connection/Rate limit indicator dot (muted unless warning)"
      ],
      "message_stream": "Use ScrollArea; keep max width for readability; show timestamps in mono.",
      "composer": "Sticky bottom input with Textarea autosize; send button; show rate-limit helper text when blocked.",
      "persistence": "When reopening /chat/:conversationId, render citations + retrieval detail panel exactly as stored."
    },
    "admin": {
      "layout": "Tabs: Users / Documents. Keep actions 1–2 clicks.",
      "users_tab": "Table of pending users with role Select + Approve button; approved users list below with role badge.",
      "documents_tab": "Upload dropzone + role checkboxes; below: documents table with editable role tags (Checkbox group in Dialog)."
    }
  },
  "3d_particles": {
    "recommendation": "Use a subtle particle field or radar sweep only in landing hero and auth backgrounds. Avoid heavy 3D in app screens to keep focus and performance.",
    "library_options": {
      "particles": {
        "lib": "tsparticles (react-tsparticles)",
        "install": "npm i react-tsparticles tsparticles",
        "config_notes": "Use low particle count (30–60), slow drift, link lines at low opacity; colors: cyan/emerald muted. Disable on prefers-reduced-motion."
      },
      "three": {
        "lib": "@react-three/fiber + drei",
        "install": "npm i @react-three/fiber @react-three/drei",
        "idea": "A faint wireframe sphere/radar ring behind hero mock panel; opacity < 0.25; no gradients on text areas."
      }
    }
  },
  "image_urls": {
    "background_textures": [
      {
        "category": "landing-hero-decor",
        "description": "Abstract grid texture; use as low-opacity overlay behind hero only.",
        "url": "https://images.unsplash.com/photo-1569456728219-580cd8147c2c?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
      },
      {
        "category": "landing-hero-decor",
        "description": "Industrial lines texture; can be blurred and used as a corner vignette.",
        "url": "https://images.unsplash.com/photo-1544185196-bd8bcb3bcca4?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
      }
    ],
    "photography": [
      {
        "category": "landing-feature-admin-kb",
        "description": "Server-room vibe photo; use very subtly (opacity 0.18) as a masked background in one feature card only.",
        "url": "https://images.unsplash.com/photo-1614508569207-3295ac89d75f?crop=entropy&cs=srgb&fm=jpg&ixlib=rb-4.1.0&q=85"
      }
    ]
  },
  "accessibility": {
    "contrast": "Ensure WCAG AA: avoid low-contrast slate text on navy; use text-slate-200 for body and text-slate-400 only for metadata.",
    "focus": "Always visible focus ring: focus-visible:ring-2 focus-visible:ring-[hsl(var(--ring))] focus-visible:ring-offset-0.",
    "keyboard": [
      "Chat: Tab cycles sidebar → message list → composer; Enter sends; Shift+Enter newline.",
      "Admin: Table rows navigable; role Select accessible; Dialog focus trap."
    ],
    "reduced_motion": "Disable particles/parallax and reduce animation durations when prefers-reduced-motion is set."
  },
  "appendix_general_ui_ux_design_guidelines": "<General UI UX Design Guidelines>\n    - You must **not** apply universal transition. Eg: `transition: all`. This results in breaking transforms. Always add transitions for specific interactive elements like button, input excluding transforms\n    - You must **not** center align the app container, ie do not add `.App { text-align: center; }` in the css file. This disrupts the human natural reading flow of text\n   - NEVER: use AI assistant Emoji characters like`🤖🧠💭💡🔮🎯📚🎭🎬🎪🎉🎊🎁🎀🎂🍰🎈🎨🎰💰💵💳🏦💎🪙💸🤑📊📈📉💹🔢🏆🥇 etc for icons. Always use **FontAwesome cdn** or **lucid-react** library already installed in the package.json\n\n **GRADIENT RESTRICTION RULE**\nNEVER use dark/saturated gradient combos (e.g., purple/pink) on any UI element.  Prohibited gradients: blue-500 to purple 600, purple 500 to pink-500, green-500 to blue-500, red to pink etc\nNEVER use dark gradients for logo, testimonial, footer etc\nNEVER let gradients cover more than 20% of the viewport.\nNEVER apply gradients to text-heavy content or reading areas.\nNEVER use gradients on small UI elements (<100px width).\nNEVER stack multiple gradient layers in the same viewport.\n\n**ENFORCEMENT RULE:**\n    • Id gradient area exceeds 20% of viewport OR affects readability, **THEN** use solid colors\n\n**How and where to use:**\n   • Section backgrounds (not content backgrounds)\n   • Hero section header content. Eg: dark to light to dark color\n   • Decorative overlays and accent elements only\n   • Hero section with 2-3 mild color\n   • Gradients creation can be done for any angle say horizontal, vertical or diagonal\n\n- For AI chat, voice application, **do not use purple color. Use color like light green, ocean blue, peach orange etc**\n\n</Font Guidelines>\n\n- Every interaction needs micro-animations - hover states, transitions, parallax effects, and entrance animations. Static = dead. \n   \n- Use 2-3x more spacing than feels comfortable. Cramped designs look cheap.\n\n- Subtle grain textures, noise overlays, custom cursors, selection states, and loading animations: separates good from extraordinary.\n   \n- Before generating UI, infer the visual style from the problem statement (palette, contrast, mood, motion) and immediately instantiate it by setting global design tokens (primary, secondary/accent, background, foreground, ring, state colors), rather than relying on any library defaults. Don't make the background dark as a default step, always understand problem first and define colors accordingly\n    Eg: - if it implies playful/energetic, choose a colorful scheme\n           - if it implies monochrome/minimal, choose a black–white/neutral scheme\n\n**Component Reuse:**\n\t- Prioritize using pre-existing components from src/components/ui when applicable\n\t- Create new components that match the style and conventions of existing components when needed\n\t- Examine existing components to understand the project's component patterns before creating new ones\n\n**IMPORTANT**: Do not use HTML based component like dropdown, calendar, toast etc. You **MUST** always use `frontend/src/components/ui/ ` only as a primary components as these are modern and stylish component\n\n**Best Practices:**\n\t- Use Shadcn/UI as the primary component library for consistency and accessibility\n\t- Import path: ./components/[component-name]\n\n**Export Conventions:**\n\t- Components MUST use named exports (export const ComponentName = ...)\n\t- Pages MUST use default exports (export default function PageName() {...})\n\n**Toasts:**\n  - Use `sonner` for toasts\"\n  - Sonner component are located in `frontend/src/components/ui/sonner.tsx`\n\nUse 2–4 color gradients, subtle textures/noise overlays, or CSS-based noise to avoid flat visuals.\n</General UI UX Design Guidelines>"
}
