import React, { useEffect, useRef, useState } from 'react';
import {
  ENGAGEMENT_FORM_META,
  normalizeAndFilterEngagementForms,
} from '../utils/engagementForms.js';
import { parseFormIdFromLocation } from '../utils/whatsappShare.js';
import GoogleFormEmbed from './GoogleFormEmbed.jsx';
import { buildWhatsAppChatUrl } from '../utils/directContact.js';
import ShareActions from './ShareActions.jsx';

const TOUCH_TARGET_STYLE = {
  minHeight: '44px',
  minWidth: '44px',
};

export function resolveSelectedEngagementForm(visibleForms = [], selectedFormId = null) {
  if (
    !Array.isArray(visibleForms) ||
    selectedFormId === null ||
    selectedFormId === undefined
  ) {
    return null;
  }
  return (
    visibleForms.find((item) => String(item?.id) === String(selectedFormId)) ?? null
  );
}

export function isCardActivationKey(key) {
  return key === 'Enter' || key === ' ';
}

export default function EngagementSection({
  forms = [],
  members = [],
  initialSelectedFormId = null,
  shareBaseUrl,
  onSelectForm,
}) {
  const [selectedFormId, setSelectedFormId] = useState(
    () =>
      initialSelectedFormId ??
      (typeof window !== 'undefined'
        ? parseFormIdFromLocation(window.location)
        : null)
  );
  const embedStageRef = useRef(null);
  const shouldScrollToEmbedRef = useRef(false);

  useEffect(() => {
    if (typeof window === 'undefined' || initialSelectedFormId !== null) {
      return undefined;
    }

    const syncFromLocation = () => {
      const formIdFromLocation = parseFormIdFromLocation(window.location);
      setSelectedFormId(formIdFromLocation);
    };

    window.addEventListener('hashchange', syncFromLocation);
    window.addEventListener('popstate', syncFromLocation);
    return () => {
      window.removeEventListener('hashchange', syncFromLocation);
      window.removeEventListener('popstate', syncFromLocation);
    };
  }, [initialSelectedFormId]);

  const visibleForms = normalizeAndFilterEngagementForms(forms, 'all');
  const selectedForm = resolveSelectedEngagementForm(visibleForms, selectedFormId);

  useEffect(() => {
    if (selectedFormId === null || selectedFormId === undefined) return;
    const stillVisible = visibleForms.some(
      (item) => String(item.id) === String(selectedFormId)
    );
    if (!stillVisible) {
      setSelectedFormId(null);
    }
  }, [visibleForms, selectedFormId]);

  useEffect(() => {
    if (shouldScrollToEmbedRef.current && selectedForm && embedStageRef.current) {
      shouldScrollToEmbedRef.current = false;
      embedStageRef.current.scrollIntoView?.({
        behavior: 'smooth',
        block: 'start',
      });
    }
  }, [selectedForm]);

  const handleSelectForm = (form) => {
    if (!form) return;
    shouldScrollToEmbedRef.current = true;
    setSelectedFormId(form.id);
    if (
      typeof window !== 'undefined' &&
      initialSelectedFormId === null &&
      form.id !== null &&
      form.id !== undefined
    ) {
      const targetHash = `#form-${encodeURIComponent(String(form.id).trim())}`;
      if (window.location.hash !== targetHash) {
        window.history.replaceState(null, '', targetHash);
      }
    }
    if (typeof onSelectForm === 'function') {
      onSelectForm(form);
    }
  };

  const contacts = (Array.isArray(members) ? members : []).filter(
    (m) => m && (m.isDirectContact ?? m.is_direct_contact) === true
  );

  return (
    <section
      id="engagement-section"
      dir="rtl"
      className="engagement-section"
      aria-labelledby="engagement-section-heading"
    >
      <div className="engagement-section__header">
        <div className="engagement-section__title-group">
          <h2 id="engagement-section-heading" className="engagement-section__title">
            التواصل والتفاعل مع اللجنة
          </h2>
          <p className="engagement-section__subtitle">
            شاركوا آراءكم ومقترحاتكم، اطلبوا المساندة، أو سجّلوا في الفعاليات المدرسية مباشرة دون الحاجة لإنشاء حساب أو تسجيل دخول.
          </p>
        </div>
      </div>

      {contacts.length > 0 && (
        <div className="direct-contacts" role="region" aria-label="جهات اتصال مباشرة مع اللجنة">
          <h3 className="direct-contacts__title">تواصل مباشر مع اللجنة</h3>
          <div className="direct-contacts__list" role="list">
            {contacts.map((c) => {
              const name = c.fullName ?? c.full_name ?? '';
              const phone = (c.phone ?? '').trim();
              const email = (c.email ?? '').trim();
              const waUrl = buildWhatsAppChatUrl(phone);
              return (
                <article key={c.id} className="direct-contact" role="listitem" dir="rtl">
                  <div className="direct-contact__identity">
                    <strong className="direct-contact__name">{name}</strong>
                    {c.role && <span className="direct-contact__role">{c.role}</span>}
                  </div>
                  <div className="direct-contact__actions">
                    {phone && (
                      <a
                        href={`tel:${phone.replace(/[^\d+]/g, '')}`}
                        className="direct-contact__btn direct-contact__btn--phone"
                        style={TOUCH_TARGET_STYLE}
                        aria-label={`اتصال هاتفي بـ ${name}`}
                      >
                        <span className="direct-contact__icon-badge" aria-hidden="true">
                          <svg
                            className="direct-contact__icon"
                            viewBox="0 0 24 24"
                            width="18"
                            height="18"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                            focusable="false"
                          >
                            <path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.79 19.79 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6 19.79 19.79 0 0 1-3.07-8.67A2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72 12.84 12.84 0 0 0 .7 2.81 2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45 12.84 12.84 0 0 0 2.81.7A2 2 0 0 1 22 16.92z" />
                          </svg>
                        </span>
                        <span className="direct-contact__label">اتصال</span>
                      </a>
                    )}
                    {waUrl && (
                      <a
                        href={waUrl}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="direct-contact__btn direct-contact__btn--whatsapp"
                        style={TOUCH_TARGET_STYLE}
                        aria-label={`مراسلة ${name} عبر واتساب`}
                      >
                        <span className="direct-contact__icon-badge" aria-hidden="true">
                          <svg
                            className="direct-contact__icon"
                            viewBox="0 0 24 24"
                            width="18"
                            height="18"
                            fill="currentColor"
                            aria-hidden="true"
                            focusable="false"
                          >
                            <path d="M12.04 2C6.58 2 2.13 6.45 2.13 11.91c0 1.75.46 3.45 1.32 4.95L2.05 22l5.25-1.38c1.45.79 3.08 1.21 4.74 1.21 5.46 0 9.91-4.45 9.91-9.91C21.95 6.45 17.5 2 12.04 2zm5.82 14.08c-.24.68-1.42 1.3-1.97 1.38-.52.08-1.18.11-1.91-.12-.44-.14-1.01-.33-1.74-.65-3.06-1.32-5.06-4.41-5.21-4.61-.15-.2-1.24-1.65-1.24-3.15s.79-2.24 1.07-2.54c.28-.3.61-.38.82-.38.2 0 .41.01.59.02.19.01.44-.07.69.53.25.6.85 2.08.93 2.23.08.15.13.33.03.53-.1.2-.15.33-.3.5-.15.18-.32.4-.46.53-.15.15-.31.32-.13.63.18.3.79 1.31 1.7 2.12 1.17 1.04 2.15 1.36 2.46 1.51.3.15.48.13.66-.08.18-.2.76-.88.96-1.18.2-.3.4-.25.68-.15.28.1 1.76.83 2.06.98.3.15.5.23.58.36.08.13.08.76-.16 1.44z" />
                          </svg>
                        </span>
                        <span className="direct-contact__label">واتساب</span>
                      </a>
                    )}
                    {email && (
                      <a
                        href={`mailto:${email}`}
                        className="direct-contact__btn direct-contact__btn--email"
                        style={TOUCH_TARGET_STYLE}
                        aria-label={`إرسال بريد إلكتروني إلى ${name}`}
                      >
                        <span className="direct-contact__icon-badge" aria-hidden="true">
                          <svg
                            className="direct-contact__icon"
                            viewBox="0 0 24 24"
                            width="18"
                            height="18"
                            fill="none"
                            stroke="currentColor"
                            strokeWidth="2"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                            aria-hidden="true"
                            focusable="false"
                          >
                            <rect x="2" y="4" width="20" height="16" rx="2" />
                            <path d="m22 7-8.97 5.7a1.94 1.94 0 0 1-2.06 0L2 7" />
                          </svg>
                        </span>
                        <span className="direct-contact__label">بريد</span>
                      </a>
                    )}
                  </div>
                </article>
              );
            })}
          </div>
        </div>
      )}

      {visibleForms.length === 0 ? (
        <div className="engagement-section__empty" role="status">
          <p>لا توجد نماذج تفاعلية مفعّلة في هذا القسم حالياً.</p>
        </div>
      ) : (
        <>
          <div className="engagement-section__cards" role="list">
            {visibleForms.map((form) => {
              const isSelected = selectedForm && String(selectedForm.id) === String(form.id);
              const meta = ENGAGEMENT_FORM_META[form.formType] ?? {
                label: form.formType,
                badge: form.formType,
              };

              return (
                <article
                  key={form.id}
                  id={`form-${String(form.id).trim()}`}
                  dir="rtl"
                  role="listitem"
                  tabIndex={0}
                  aria-label={`فتح ${form.title}`}
                  data-selected={isSelected ? 'true' : 'false'}
                  className={`engagement-card engagement-card--clickable ${
                    isSelected ? 'engagement-card--active' : ''
                  }`.trim()}
                  onClick={() => handleSelectForm(form)}
                  onKeyDown={(event) => {
                    if (isCardActivationKey(event.key)) {
                      event.preventDefault();
                      handleSelectForm(form);
                    }
                  }}
                >
                  <div className="engagement-card__top">
                    <span
                      className={`engagement-card__badge engagement-card__badge--${form.formType}`}
                    >
                      {meta.badge}
                    </span>
                    <span className="engagement-card__provider">
                      <bdi dir="ltr">Google Forms</bdi>
                    </span>
                  </div>

                  <h3 className="engagement-card__title">{form.title}</h3>
                  {form.description && (
                    <p className="engagement-card__description">{form.description}</p>
                  )}

                  <div
                    className="engagement-card__share"
                    onClick={(event) => event.stopPropagation()}
                    onKeyDown={(event) => event.stopPropagation()}
                  >
                    <ShareActions
                      item={form}
                      entityType="form"
                      baseUrl={shareBaseUrl}
                    />
                  </div>
                </article>
              );
            })}
          </div>

          {selectedForm && (
            <div
              ref={embedStageRef}
              className="engagement-section__embed-stage"
            >
              <GoogleFormEmbed
                form={selectedForm}
                shareBaseUrl={shareBaseUrl}
              />
            </div>
          )}
        </>
      )}
    </section>
  );
}
