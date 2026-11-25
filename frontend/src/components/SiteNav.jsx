import React, { useEffect, useRef, useState } from 'react';

export const PAGES = [
  { id: 'announcements', label: 'لوحة الإعلانات والفعاليات' },
  { id: 'engagement', label: 'التواصل والتفاعل مع اللجنة' },
  { id: 'committee', label: 'أعضاء لجنة أولياء الأمور' },
];

export default function SiteNav({ view, currentPage, onNavigate, onOpenAdmin, onExitAdmin }) {
  const [open, setOpen] = useState(false);
  const navRef = useRef(null);
  const toggleRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key === 'Escape') {
        setOpen(false);
        toggleRef.current?.focus();
      }
    };
    const onPointerDown = (e) => {
      if (navRef.current && !navRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [open]);

  const select = (fn) => (e) => {
    if (e) e.preventDefault();
    setOpen(false);
    fn();
  };

  return (
    <nav ref={navRef} className="site-nav" aria-label="التنقل الرئيسي">
      <div className="site-nav__inner">
        <button
          ref={toggleRef}
          type="button"
          className="site-nav__toggle"
          aria-expanded={open}
          aria-controls="site-nav-menu"
          aria-label={open ? 'إغلاق القائمة' : 'فتح القائمة'}
          onClick={() => setOpen((v) => !v)}
        >
          <span className="site-nav__burger" aria-hidden="true" />
          <span className="site-nav__toggle-label">القائمة</span>
        </button>

        <ul
          id="site-nav-menu"
          className={`site-nav__list${open ? ' site-nav__list--open' : ''}`}
        >
          {view === 'admin' ? (
            <li>
              <button
                type="button"
                className="site-nav__link"
                onClick={select(onExitAdmin)}
              >
                العودة إلى المنصة العامة
              </button>
            </li>
          ) : (
            <>
              {PAGES.map((page) => {
                const active = page.id === currentPage;
                return (
                  <li key={page.id}>
                    <a
                      href={`#${page.id}`}
                      className={`site-nav__link${active ? ' site-nav__link--active' : ''}`}
                      aria-current={active ? 'page' : undefined}
                      onClick={select(() => onNavigate(page.id))}
                    >
                      {page.label}
                    </a>
                  </li>
                );
              })}
              <li className="site-nav__admin-item">
                <button
                  type="button"
                  className="site-nav__link site-nav__link--admin"
                  onClick={select(onOpenAdmin)}
                >
                  لوحة الإدارة
                </button>
              </li>
            </>
          )}
        </ul>
      </div>
    </nav>
  );
}
