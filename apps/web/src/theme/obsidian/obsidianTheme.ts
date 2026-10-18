/**
 * inteGREAT "obsidian" theme — extends Astryx gothic (D-021).
 *
 * Owner direction: Obsidian-faithful dark UI. Charcoal surfaces, muted text, one soft purple accent,
 * and colour used only to mean something (conflict / failed / suspect / verified / observed).
 * Overrides gothic's blackletter display type, large type scale and slow "theatrical" motion.
 * Fonts are bundled locally via @fontsource-variable (no network font loading) so offline demos look the same.
 */
import {defineTheme} from '@astryxdesign/core/theme';
import {gothicTheme} from '@astryxdesign/theme-gothic';

const SANS = '"Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, Roboto, Helvetica, Arial, sans-serif';

export const obsidianTheme = defineTheme({
  name: 'obsidian',
  extends: gothicTheme,
  typography: {
    scale: {base: 14, ratio: 1.2},
    body: {family: 'Inter Variable', fallbacks: `Inter, ${SANS}`},
    heading: {family: 'Inter Variable', fallbacks: `Inter, ${SANS}`, weights: {3: 'bold', 4: 'bold'}},
    code: {family: 'JetBrains Mono Variable', fallbacks: 'JetBrains Mono, Cascadia Code, Consolas, "SF Mono", Menlo, monospace'},
  },
  motion: {fast: 100, medium: 180, slow: 300, ratio: 0.75},
  tokens: {
    // Surfaces (Obsidian default dark)
    '--color-background-body': '#1e1e1e',
    '--color-background-surface': '#1e1e1e',
    '--color-background-card': '#262626',
    '--color-background-muted': '#2a2a2a',
    '--color-background-popover': '#2b2b2b',
    '--color-background-inverted': '#dcddde',
    '--color-border': '#ffffff14',
    '--color-border-emphasized': '#3f3f3f',
    '--color-neutral': '#ffffff14',
    '--color-overlay': '#000000b3',
    '--color-overlay-hover': '#ffffff0d',
    '--color-overlay-pressed': '#ffffff1a',
    '--color-shadow': '#00000066',
    '--color-skeleton': '#3a3a3a',

    // Text + icons
    '--color-text-primary': '#dcddde',
    '--color-text-secondary': '#999999',
    '--color-text-disabled': '#5c5c5c',
    '--color-text-accent': '#a99bf9',
    '--color-icon-primary': '#dcddde',
    '--color-icon-secondary': '#999999',
    '--color-icon-disabled': '#5c5c5c',
    '--color-icon-accent': '#a99bf9',
    '--color-on-dark': '#dcddde',
    '--color-on-light': '#1e1e1e',

    // The one accent: Obsidian purple
    '--color-accent': '#8b7cf6',
    '--color-accent-muted': '#8b7cf626',
    '--color-on-accent': '#ffffff',

    // Status — saturated enough to read at a glance on charcoal
    '--color-error': '#e5534b',
    '--color-error-muted': '#e5534b26',
    '--color-on-error': '#ffffff',
    '--color-warning': '#e0af68',
    '--color-warning-muted': '#e0af6826',
    '--color-on-warning': '#1e1e1e',
    '--color-success': '#4fb67d',
    '--color-success-muted': '#4fb67d26',
    '--color-on-success': '#10140f',
  },
});

export default obsidianTheme;
