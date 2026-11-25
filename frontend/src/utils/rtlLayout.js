export const RTL_DIRECTION = 'rtl';
export const ARABIC_LANG = 'ar';
export const MIN_TOUCH_TARGET_PX = 44;

export const ARABIC_FONT_FAMILIES = Object.freeze([
  'Tajawal',
  'Cairo',
  'Noto Sans Arabic',
]);

export const RESPONSIVE_BREAKPOINTS = Object.freeze({
  mobile: 0,
  sm: 640,
  md: 768,
  lg: 1024,
  xl: 1280,
});

export const TOUCH_TARGET_STYLE = Object.freeze({
  minHeight: `${MIN_TOUCH_TARGET_PX}px`,
  minWidth: `${MIN_TOUCH_TARGET_PX}px`,
});

export const RTL_ROOT_ATTRIBUTES = Object.freeze({
  dir: RTL_DIRECTION,
  lang: ARABIC_LANG,
});

/**
 * Enforce dir="rtl" and lang="ar" on the root document elements at runtime.
 */
export function enforceDocumentRtl(
  doc = typeof document !== 'undefined' ? document : null
) {
  if (!doc || !doc.documentElement) {
    return { applied: false, dir: RTL_DIRECTION, lang: ARABIC_LANG };
  }

  const root = doc.documentElement;
  root.dir = RTL_DIRECTION;
  root.lang = ARABIC_LANG;
  if (typeof root.setAttribute === 'function') {
    root.setAttribute('dir', RTL_DIRECTION);
    root.setAttribute('lang', ARABIC_LANG);
  }

  if (doc.body) {
    doc.body.dir = RTL_DIRECTION;
    if (typeof doc.body.setAttribute === 'function') {
      doc.body.setAttribute('dir', RTL_DIRECTION);
    }
  }

  return { applied: true, dir: RTL_DIRECTION, lang: ARABIC_LANG };
}

/**
 * Classify a viewport width into the mobile-first responsive tier.
 */
export function resolveViewportTier(width) {
  if (typeof width !== 'number' || !Number.isFinite(width) || width < 0) {
    return 'mobile';
  }
  if (width >= RESPONSIVE_BREAKPOINTS.xl) return 'xl';
  if (width >= RESPONSIVE_BREAKPOINTS.lg) return 'lg';
  if (width >= RESPONSIVE_BREAKPOINTS.md) return 'md';
  if (width >= RESPONSIVE_BREAKPOINTS.sm) return 'sm';
  return 'mobile';
}
