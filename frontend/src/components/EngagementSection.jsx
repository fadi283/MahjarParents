import React, { useEffect, useState } from 'react';
import {
  ENGAGEMENT_FORM_META,
  ENGAGEMENT_FORM_TYPES,
  normalizeAndFilterEngagementForms,
} from '../utils/engagementForms.js';
import { parseFormIdFromLocation } from '../utils/whatsappShare.js';
import GoogleFormEmbed from './GoogleFormEmbed.jsx';
import ShareActions from './ShareActions.jsx';

const TOUCH_TARGET_STYLE = {
  minHeight: '44px',
  minWidth: '44px',
};

export default function EngagementSection({
  forms = [],
  initialFormType = 'all',
  initialSelectedFormId = null,
  shareBaseUrl,
  onFormTypeChange,
  onSelectForm,
}) {
  const [activeFormType, setActiveFormType] = useState(initialFormType);
  const [selectedFormId, setSelectedFormId] = useState(
    () =>
      initialSelectedFormId ??
      (typeof window !== 'undefined'
        ? parseFormIdFromLocation(window.location)
        : null)
  );

  useEffect(() => {
    if (typeof window === 'undefined' || initialSelectedFormId !== null) {
      return undefined;
    }

    const syncFromLocation = () => {
      const formIdFromLocation = parseFormIdFromLocation(window.location);
      if (formIdFromLocation !== null) {
        setActiveFormType('all');
        setSelectedFormId(formIdFromLocation);
      }
    };

    window.addEventListener('hashchange', syncFromLocation);
    window.addEventListener('popstate', syncFromLocation);
    return () => {
      window.removeEventListener('hashchange', syncFromLocation);
      window.removeEventListener('popstate', syncFromLocation);
    };
  }, [initialSelectedFormId]);

  const visibleForms = normalizeAndFilterEngagementForms(forms, activeFormType);

  const selectedForm =
    visibleForms.find(
      (item) =>
        selectedFormId !== null &&
        selectedFormId !== undefined &&
        String(item.id) === String(selectedFormId)
    ) ??
    visibleForms[0] ??
    null;

  useEffect(() => {
    if (visibleForms.length === 0) return;
    const stillVisible = visibleForms.some(
      (item) => String(item.id) === String(selectedFormId)
    );
    if (!stillVisible) {
      setSelectedFormId(visibleForms[0].id);
    }
  }, [visibleForms, selectedFormId]);

  const handleSelectType = (typeId) => {
    setActiveFormType(typeId);
    const nextVisible = normalizeAndFilterEngagementForms(forms, typeId);
    setSelectedFormId(nextVisible[0]?.id ?? null);
    if (typeof onFormTypeChange === 'function') {
      onFormTypeChange(typeId);
    }
  };

  const handleSelectForm = (form) => {
    if (!form) return;
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

  return (
    <section
      id="engagement-section"
      dir="rtl"
      className="engagement-section"
      aria-labelledby="engagement-section-heading"
    >
      <div className="engagement-section__header">
        <div className="engagement-section__title-group">
          <span className="engagement-section__zero-login">
            تفاعل مباشر • بدون تسجيل دخول
          </span>
          <h2 id="engagement-section-heading" className="engagement-section__title">
            التواصل والتفاعل مع اللجنة
          </h2>
          <p className="engagement-section__subtitle">
            شاركوا آراءكم ومقترحاتكم، اطلبوا المساندة، أو سجّلوا في الفعاليات المدرسية مباشرة دون الحاجة لإنشاء حساب أو تسجيل دخول.
          </p>
        </div>

        <div
          className="engagement-section__filters"
          role="toolbar"
          aria-label="تصفية النماذج التفاعلية حسب النوع"
        >
          {ENGAGEMENT_FORM_TYPES.map((typeOption) => {
            const isActive = activeFormType === typeOption.id;
            return (
              <button
                key={typeOption.id}
                type="button"
                className={`engagement-section__filter-btn ${
                  isActive ? 'engagement-section__filter-btn--active' : ''
                }`}
                style={TOUCH_TARGET_STYLE}
                aria-pressed={isActive ? 'true' : 'false'}
                data-form-type={typeOption.id}
                onClick={() => handleSelectType(typeOption.id)}
              >
                {typeOption.label}
              </button>
            );
          })}
        </div>
      </div>

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
                  className={`engagement-card ${
                    isSelected ? 'engagement-card--active' : ''
                  }`}
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

                  <div className="engagement-card__actions">
                    <button
                      type="button"
                      className={`engagement-card__select-btn ${
                        isSelected ? 'engagement-card__select-btn--active' : ''
                      }`}
                      style={TOUCH_TARGET_STYLE}
                      aria-pressed={isSelected ? 'true' : 'false'}
                      onClick={() => handleSelectForm(form)}
                    >
                      {isSelected ? 'النموذج معروض أدناه' : 'تعبئة النموذج هنا'}
                    </button>

                    <a
                      href={form.directUrl}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="engagement-card__fallback-link"
                      style={TOUCH_TARGET_STYLE}
                    >
                      فتح مباشر
                    </a>
                  </div>

                  <div className="engagement-card__share">
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
            <div className="engagement-section__embed-stage">
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
