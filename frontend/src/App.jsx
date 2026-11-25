import React, { useCallback, useEffect, useState } from 'react';
import AnnouncementsFeed from './components/AnnouncementsFeed.jsx';
import CommitteeDirectory from './components/CommitteeDirectory.jsx';
import EngagementSection from './components/EngagementSection.jsx';
import SiteNav, { PAGES } from './components/SiteNav.jsx';
import AdminDashboard from './components/admin/AdminDashboard.jsx';
import { defaultAnnouncementsPosts } from './data/announcementsPosts.js';
import { defaultCommitteeMembers } from './data/committeeMembers.js';
import { defaultEngagementForms } from './data/engagementForms.js';
import { API_BASE_URL, buildApiUrl } from './utils/apiConfig.js';
import { enforceDocumentRtl, RTL_ROOT_ATTRIBUTES } from './utils/rtlLayout.js';
import './styles.css';

const PAGE_IDS = PAGES.map((p) => p.id);
const DEFAULT_PAGE = PAGE_IDS[0];

function resolvePageFromHash() {
  if (typeof window === 'undefined') return DEFAULT_PAGE;
  const hash = window.location.hash.replace(/^#\/?/, '');
  return PAGE_IDS.includes(hash) ? hash : DEFAULT_PAGE;
}

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
  initialPage,
  adminProps = {},
}) {
  const [view, setView] = useState(() => resolveInitialView(initialView));
  const [page, setPage] = useState(() =>
    PAGE_IDS.includes(initialPage) ? initialPage : resolvePageFromHash()
  );
  const [liveMembers, setLiveMembers] = useState(members);
  const [livePosts, setLivePosts] = useState(posts);
  const [liveForms, setLiveForms] = useState(forms);

  useEffect(() => {
    enforceDocumentRtl();
  }, []);

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
      setPage(resolvePageFromHash());
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
            (API_BASE_URL
              ? fetch(buildApiUrl('/api/committee'))
              : fetch('/api/committee')
            ).then((r) => (r.ok ? r.json() : null))
          );
        } else {
          requests.push(Promise.resolve(null));
        }
        if (usesDefaultPosts) {
          requests.push(
            (API_BASE_URL
              ? fetch(buildApiUrl('/api/posts'))
              : fetch('/api/posts')
            ).then((r) => (r.ok ? r.json() : null))
          );
        } else {
          requests.push(Promise.resolve(null));
        }
        if (usesDefaultForms) {
          requests.push(
            (API_BASE_URL
              ? fetch(buildApiUrl('/api/forms'))
              : fetch('/api/forms')
            ).then((r) => (r.ok ? r.json() : null))
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
      } else if (window.location.hash === '#admin' || window.location.pathname === '/admin') {
        window.history.pushState(null, '', `${window.location.pathname === '/admin' ? '/' : window.location.pathname}#${page}`);
      }
    }
  };

  const navigatePage = (nextPage) => {
    setView('public');
    setPage(nextPage);
    if (typeof window !== 'undefined') {
      if (!initialView && window.location.hash !== `#${nextPage}`) {
        window.history.pushState(null, '', `#${nextPage}`);
      }
      window.scrollTo?.({ top: 0 });
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
    <main {...RTL_ROOT_ATTRIBUTES} className="app-container">
      <header className="app-header">
        <div className="app-header__inner app-header__brand">
          <div className="app-header__text">
            <span className="app-header__badge">مدرسة المحجر الابتدائية - أم الفحم</span>
            <h1 className="app-header__title">
              لجنة أولياء أمور الطلاب
            </h1>
            <p className="app-header__subtitle">
              المنصة الرقمية للتواصل المجتمعي والشراكة التربوية مع الأهالي
            </p>
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

      <SiteNav
        view={view}
        currentPage={page}
        onNavigate={navigatePage}
        onOpenAdmin={() => navigateTo('admin')}
        onExitAdmin={() => navigateTo('public')}
      />

      <div className="app-content">
        {view === 'admin' ? (
          <AdminDashboard
            onExitAdmin={() => navigateTo('public')}
            onDataChanged={handleAdminDataChanged}
            {...adminProps}
          />
        ) : (
          <>
            {page === 'announcements' && <AnnouncementsFeed posts={livePosts} />}
            {page === 'engagement' && <EngagementSection forms={liveForms} />}
            {page === 'committee' && <CommitteeDirectory members={liveMembers} />}
          </>
        )}
      </div>
    </main>
  );
}
