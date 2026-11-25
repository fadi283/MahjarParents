import React, { useCallback, useEffect, useState } from 'react';
import AnnouncementsFeed from './components/AnnouncementsFeed.jsx';
import CommitteeDirectory from './components/CommitteeDirectory.jsx';
import EngagementSection from './components/EngagementSection.jsx';
import AdminDashboard from './components/admin/AdminDashboard.jsx';
import { TOUCH_TARGET_STYLE } from './components/admin/adminShared.jsx';
import { defaultAnnouncementsPosts } from './data/announcementsPosts.js';
import { defaultCommitteeMembers } from './data/committeeMembers.js';
import { defaultEngagementForms } from './data/engagementForms.js';
import './styles.css';

function resolveInitialView(explicitView) {
  if (explicitView === 'admin' || explicitView === 'public') {
    return explicitView;
  }
  if (typeof window !== 'undefined') {
    if (window.location.pathname === '/admin' || window.location.hash === '#admin') {
      return 'admin';
    }
  }
  return 'public';
}

export default function App({
  members = defaultCommitteeMembers,
  posts = defaultAnnouncementsPosts,
  forms = defaultEngagementForms,
  initialView,
  adminProps = {},
}) {
  const [view, setView] = useState(() => resolveInitialView(initialView));
  const [liveMembers, setLiveMembers] = useState(members);
  const [livePosts, setLivePosts] = useState(posts);
  const [liveForms, setLiveForms] = useState(forms);

  useEffect(() => {
    setLiveMembers(members);
  }, [members]);

  useEffect(() => {
    setLivePosts(posts);
  }, [posts]);

  useEffect(() => {
    setLiveForms(forms);
  }, [forms]);

  useEffect(() => {
    if (typeof window === 'undefined') return undefined;

    const syncFromLocation = () => {
      if (initialView) return;
      if (window.location.pathname === '/admin' || window.location.hash === '#admin') {
        setView('admin');
      } else {
        setView('public');
      }
    };

    window.addEventListener('hashchange', syncFromLocation);
    window.addEventListener('popstate', syncFromLocation);
    return () => {
      window.removeEventListener('hashchange', syncFromLocation);
      window.removeEventListener('popstate', syncFromLocation);
    };
  }, [initialView]);

  useEffect(() => {
    if (typeof fetch !== 'function') return undefined;
    const usesDefaultMembers = members === defaultCommitteeMembers;
    const usesDefaultPosts = posts === defaultAnnouncementsPosts;
    const usesDefaultForms = forms === defaultEngagementForms;
    if (!usesDefaultMembers && !usesDefaultPosts && !usesDefaultForms) return undefined;

    let cancelled = false;
    async function hydratePublicContent() {
      try {
        const requests = [];
        if (usesDefaultMembers) {
          requests.push(
            fetch('/api/committee').then((r) => (r.ok ? r.json() : null))
          );
        } else {
          requests.push(Promise.resolve(null));
        }
        if (usesDefaultPosts) {
          requests.push(
            fetch('/api/posts').then((r) => (r.ok ? r.json() : null))
          );
        } else {
          requests.push(Promise.resolve(null));
        }
        if (usesDefaultForms) {
          requests.push(
            fetch('/api/forms').then((r) => (r.ok ? r.json() : null))
          );
        } else {
          requests.push(Promise.resolve(null));
        }

        const [fetchedMembers, fetchedPosts, fetchedForms] = await Promise.all(requests);
        if (cancelled) return;
        if (Array.isArray(fetchedMembers)) {
          setLiveMembers(fetchedMembers);
        }
        if (Array.isArray(fetchedPosts)) {
          setLivePosts(fetchedPosts);
        }
        if (Array.isArray(fetchedForms)) {
          setLiveForms(fetchedForms);
        } else if (Array.isArray(fetchedForms?.items)) {
          setLiveForms(fetchedForms.items);
        }
      } catch {
        // Keep bundled fallback data when backend API is unavailable
      }
    }

    hydratePublicContent();
    return () => {
      cancelled = true;
    };
  }, [members, posts, forms]);

  const navigateTo = (nextView) => {
    setView(nextView);
    if (typeof window !== 'undefined' && !initialView) {
      if (nextView === 'admin') {
        if (window.location.hash !== '#admin') {
          window.history.pushState(null, '', '#admin');
        }
      } else if (window.location.hash === '#admin') {
        window.history.pushState(null, '', window.location.pathname || '/');
      } else if (window.location.pathname === '/admin') {
        window.history.pushState(null, '', '/');
      }
    }
  };

  const handleAdminDataChanged = useCallback((nextData) => {
    if (Array.isArray(nextData?.committee)) {
      setLiveMembers(nextData.committee);
    }
    if (Array.isArray(nextData?.posts)) {
      setLivePosts(nextData.posts);
    }
    if (Array.isArray(nextData?.forms)) {
      setLiveForms(nextData.forms);
    }
  }, []);

  return (
    <main dir="rtl" className="app-container">
      <header className="app-header">
        <div className="app-header__inner app-header__brand">
          <div className="app-header__text">
            <span className="app-header__badge">مدرسة المحجر الابتدائية</span>
            <h1 className="app-header__title">
              لجنة أولياء أمور الطلاب – مدرسة المحجر الابتدائية
            </h1>
            <p className="app-header__subtitle">
              المنصة الرقمية للتواصل المجتمعي والشراكة التربوية مع الأهالي
            </p>
            <div className="app-header__nav">
              {view === 'admin' ? (
                <button
                  type="button"
                  className="app-header__admin-btn"
                  style={TOUCH_TARGET_STYLE}
                  onClick={() => navigateTo('public')}
                >
                  العودة إلى المنصة العامة
                </button>
              ) : (
                <>
                  <a
                    href="#engagement-section"
                    className="app-header__quick-link"
                    style={TOUCH_TARGET_STYLE}
                  >
                    التفاعل والنماذج
                  </a>
                  <button
                    type="button"
                    className="app-header__admin-btn"
                    style={TOUCH_TARGET_STYLE}
                    onClick={() => navigateTo('admin')}
                  >
                    لوحة الإدارة
                  </button>
                </>
              )}
            </div>
          </div>
          <div className="app-header__logo-wrapper">
            <img
              src="/logo.jpg"
              alt="شعار لجنة أولياء أمور مدرسة المحجر الابتدائية"
              className="app-header__logo"
              width="140"
              height="140"
            />
          </div>
        </div>
      </header>

      <div className="app-content">
        {view === 'admin' ? (
          <AdminDashboard
            onExitAdmin={() => navigateTo('public')}
            onDataChanged={handleAdminDataChanged}
            {...adminProps}
          />
        ) : (
          <>
            <AnnouncementsFeed posts={livePosts} />
            <EngagementSection forms={liveForms} />
            <CommitteeDirectory members={liveMembers} />
          </>
        )}
      </div>
    </main>
  );
}
