import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adminApi, translateAdminError } from '../../utils/adminApi.js';
import {
  removeById,
  syncMediaLinksIntoPosts,
  upsertCommitteeList,
  upsertFormList,
  upsertMediaLinkList,
  upsertPostList,
} from '../../utils/adminState.js';
import AdminLoginForm from './AdminLoginForm.jsx';
import CommitteeAdminPanel from './CommitteeAdminPanel.jsx';
import PostsAdminPanel from './PostsAdminPanel.jsx';
import MediaLinksAdminPanel from './MediaLinksAdminPanel.jsx';
import FormsAdminPanel from './FormsAdminPanel.jsx';
import { TOUCH_TARGET_STYLE } from './adminShared.jsx';

export const ADMIN_SECTIONS = [
  { id: 'committee', label: 'أعضاء اللجنة' },
  { id: 'posts', label: 'الإعلانات والفعاليات' },
  { id: 'media', label: 'روابط الوسائط' },
  { id: 'forms', label: 'نماذج Google Forms' },
];

export default function AdminDashboard({
  apiClient = adminApi,
  onExitAdmin,
  onDataChanged,
  initialAuth = null,
  initialSection = 'committee',
  initialData = null,
  initialError = '',
  initialEditingItem = null,
}) {
  const [auth, setAuth] = useState(initialAuth);
  const [checkingSession, setCheckingSession] = useState(() =>
    Boolean(
      !initialAuth &&
        typeof window !== 'undefined' &&
        apiClient.getStoredToken?.()
    )
  );
  const [activeSection, setActiveSection] = useState(initialSection);
  const [committee, setCommittee] = useState(() => initialData?.committee ?? []);
  const [posts, setPosts] = useState(() => initialData?.posts ?? []);
  const [mediaLinks, setMediaLinks] = useState(() => initialData?.mediaLinks ?? []);
  const [forms, setForms] = useState(() => initialData?.forms ?? []);
  const [isBusy, setIsBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState(initialError);
  const [statusMessage, setStatusMessage] = useState('');

  const onDataChangedRef = useRef(onDataChanged);
  onDataChangedRef.current = onDataChanged;

  const notifyParent = useCallback((nextState) => {
    if (typeof onDataChangedRef.current === 'function') {
      onDataChangedRef.current(nextState);
    }
  }, []);

  const handleSessionExpired = useCallback(
    (err) => {
      if (err?.isAuthError) {
        apiClient.clearStoredToken?.();
        setAuth(null);
        setStatusMessage('');
        setErrorMessage(
          translateAdminError(err) || 'انتهت صلاحية جلسة الإدارة، يرجى تسجيل الدخول مجدداً.'
        );
        return true;
      }
      return false;
    },
    [apiClient]
  );

  const loadAllAdminData = useCallback(async () => {
    const [committeeRes, postsRes, mediaRes, formsRes] = await Promise.all([
      apiClient.listCommittee(),
      apiClient.listPosts(),
      apiClient.listMediaLinks(),
      apiClient.listForms(),
    ]);
    const nextCommittee = Array.isArray(committeeRes) ? committeeRes : [];
    const nextMedia = Array.isArray(mediaRes) ? mediaRes : [];
    const nextPosts = syncMediaLinksIntoPosts(
      Array.isArray(postsRes) ? postsRes : [],
      nextMedia
    );
    const nextForms = Array.isArray(formsRes) ? formsRes : [];

    setCommittee(nextCommittee);
    setPosts(nextPosts);
    setMediaLinks(nextMedia);
    setForms(nextForms);
    notifyParent({
      committee: nextCommittee,
      posts: nextPosts,
      mediaLinks: nextMedia,
      forms: nextForms,
    });
  }, [apiClient, notifyParent]);

  useEffect(() => {
    if (initialAuth) return;
    let active = true;

    async function bootstrapSession() {
      setCheckingSession(true);
      try {
        const sessionInfo = await apiClient.getSession();
        if (!active) return;
        if (sessionInfo?.authenticated) {
          setAuth(sessionInfo);
          if (!initialData) {
            await loadAllAdminData();
          }
        } else {
          setAuth(null);
        }
      } catch {
        if (active) {
          setAuth(null);
        }
      } finally {
        if (active) {
          setCheckingSession(false);
        }
      }
    }

    bootstrapSession();
    return () => {
      active = false;
    };
  }, [apiClient, initialAuth, initialData, loadAllAdminData]);

  const handleLogin = async (username, password) => {
    setIsBusy(true);
    setErrorMessage('');
    setStatusMessage('');
    try {
      const loginInfo = await apiClient.login(username, password);
      setAuth({
        authenticated: true,
        username: loginInfo?.username ?? username,
      });
      await loadAllAdminData();
      setStatusMessage('تم تسجيل الدخول إلى لوحة الإدارة بنجاح.');
    } catch (err) {
      setAuth(null);
      setErrorMessage(translateAdminError(err));
    } finally {
      setIsBusy(false);
    }
  };

  const handleLogout = async () => {
    setIsBusy(true);
    setErrorMessage('');
    setStatusMessage('');
    try {
      await apiClient.logout();
    } catch {
      // Token is always cleared client-side in apiClient.logout()
    } finally {
      setAuth(null);
      setIsBusy(false);
    }
  };

  const runMutation = async (operation, successText) => {
    setIsBusy(true);
    setErrorMessage('');
    setStatusMessage('');
    try {
      await operation();
      setStatusMessage(successText);
      return true;
    } catch (err) {
      if (!handleSessionExpired(err)) {
        setErrorMessage(translateAdminError(err));
      }
      return false;
    } finally {
      setIsBusy(false);
    }
  };

  const handleUploadImage = async (file) => {
    setErrorMessage('');
    try {
      const uploaded = await apiClient.uploadImage(file);
      return uploaded?.url ?? '';
    } catch (err) {
      setErrorMessage(translateAdminError(err));
      throw err;
    }
  };

  if (checkingSession) {
    return (
      <section dir="rtl" className="admin-shell" aria-busy="true">
        <div className="admin-loading" role="status">
          جارٍ التحقق من جلسة الإدارة...
        </div>
      </section>
    );
  }

  if (!auth?.authenticated) {
    return (
      <section dir="rtl" className="admin-shell">
        <AdminLoginForm
          onLogin={handleLogin}
          onCancel={onExitAdmin}
          isLoading={isBusy}
          error={errorMessage}
        />
      </section>
    );
  }

  const sectionCounts = {
    committee: committee.length,
    posts: posts.length,
    media: mediaLinks.length,
    forms: forms.length,
  };

  return (
    <section dir="rtl" className="admin-shell" aria-labelledby="admin-dashboard-heading">
      <div className="admin-topbar">
        <div className="admin-topbar__info">
          <h2 id="admin-dashboard-heading" className="admin-topbar__title">
            لوحة إدارة محتوى اللجنة
          </h2>
          <p className="admin-topbar__user">
            مسجل الدخول باسم: <strong>{auth.username}</strong>
          </p>
        </div>

        <div className="admin-topbar__actions">
          {typeof onExitAdmin === 'function' && (
            <button
              type="button"
              className="admin-btn admin-btn--secondary"
              style={TOUCH_TARGET_STYLE}
              onClick={onExitAdmin}
              disabled={isBusy}
            >
              العودة للمنصة
            </button>
          )}
          <button
            type="button"
            className="admin-btn admin-btn--danger-outline"
            style={TOUCH_TARGET_STYLE}
            onClick={handleLogout}
            disabled={isBusy}
          >
            تسجيل الخروج
          </button>
        </div>
      </div>

      {statusMessage && (
        <div className="admin-alert admin-alert--success" role="status">
          {statusMessage}
        </div>
      )}

      {errorMessage && (
        <div className="admin-alert admin-alert--error" role="alert">
          {errorMessage}
        </div>
      )}

      <div
        className="admin-tabs"
        role="tablist"
        aria-label="أقسام إدارة محتوى المنصة"
      >
        {ADMIN_SECTIONS.map((section) => {
          const isSelected = activeSection === section.id;
          return (
            <button
              key={section.id}
              id={`admin-tab-${section.id}`}
              type="button"
              role="tab"
              aria-selected={isSelected ? 'true' : 'false'}
              aria-controls={`admin-tabpanel-${section.id}`}
              className={`admin-tabs__btn ${
                isSelected ? 'admin-tabs__btn--active' : ''
              }`}
              style={TOUCH_TARGET_STYLE}
              onClick={() => {
                setActiveSection(section.id);
                setErrorMessage('');
                setStatusMessage('');
              }}
            >
              <span>{section.label}</span>
              <span className="admin-tabs__count">{sectionCounts[section.id]}</span>
            </button>
          );
        })}
      </div>

      <div
        id={`admin-tabpanel-${activeSection}`}
        role="tabpanel"
        aria-labelledby={`admin-tab-${activeSection}`}
        className="admin-tabpanel"
      >
        {activeSection === 'committee' && (
          <CommitteeAdminPanel
            members={committee}
            isBusy={isBusy}
            initialEditingItem={initialEditingItem}
            onUploadImage={handleUploadImage}
            onCreate={(payload) =>
              runMutation(async () => {
                const created = await apiClient.createCommitteeMember(payload);
                const nextCommittee = upsertCommitteeList(committee, created);
                setCommittee(nextCommittee);
                notifyParent({ committee: nextCommittee, posts, mediaLinks, forms });
              }, 'تمت إضافة عضو اللجنة بنجاح.')
            }
            onUpdate={(id, payload) =>
              runMutation(async () => {
                const updated = await apiClient.updateCommitteeMember(id, payload);
                const nextCommittee = upsertCommitteeList(committee, updated);
                setCommittee(nextCommittee);
                notifyParent({ committee: nextCommittee, posts, mediaLinks, forms });
              }, 'تم تحديث بيانات عضو اللجنة بنجاح.')
            }
            onDelete={(id) =>
              runMutation(async () => {
                await apiClient.deleteCommitteeMember(id);
                const nextCommittee = removeById(committee, id);
                setCommittee(nextCommittee);
                notifyParent({ committee: nextCommittee, posts, mediaLinks, forms });
              }, 'تم حذف عضو اللجنة بنجاح.')
            }
          />
        )}

        {activeSection === 'posts' && (
          <PostsAdminPanel
            posts={posts}
            isBusy={isBusy}
            initialEditingItem={initialEditingItem}
            onUploadImage={handleUploadImage}
            onCreate={(payload) =>
              runMutation(async () => {
                const created = await apiClient.createPost(payload);
                const nextPosts = syncMediaLinksIntoPosts(
                  upsertPostList(posts, created),
                  mediaLinks
                );
                setPosts(nextPosts);
                notifyParent({ committee, posts: nextPosts, mediaLinks, forms });
              }, 'تم نشر الإعلان بنجاح.')
            }
            onUpdate={(id, payload) =>
              runMutation(async () => {
                const updated = await apiClient.updatePost(id, payload);
                const nextPosts = syncMediaLinksIntoPosts(
                  upsertPostList(posts, updated),
                  mediaLinks
                );
                setPosts(nextPosts);
                notifyParent({ committee, posts: nextPosts, mediaLinks, forms });
              }, 'تم تحديث الإعلان بنجاح.')
            }
            onDelete={(id) =>
              runMutation(async () => {
                await apiClient.deletePost(id);
                const nextMedia = mediaLinks.filter(
                  (link) => String(link.postId) !== String(id)
                );
                const nextPosts = removeById(posts, id);
                setMediaLinks(nextMedia);
                setPosts(nextPosts);
                notifyParent({
                  committee,
                  posts: nextPosts,
                  mediaLinks: nextMedia,
                  forms,
                });
              }, 'تم حذف الإعلان بنجاح.')
            }
          />
        )}

        {activeSection === 'media' && (
          <MediaLinksAdminPanel
            mediaLinks={mediaLinks}
            posts={posts}
            isBusy={isBusy}
            initialEditingItem={initialEditingItem}
            onCreate={(payload) =>
              runMutation(async () => {
                const created = await apiClient.createMediaLink(payload);
                const nextMedia = upsertMediaLinkList(mediaLinks, created);
                const nextPosts = syncMediaLinksIntoPosts(posts, nextMedia);
                setMediaLinks(nextMedia);
                setPosts(nextPosts);
                notifyParent({
                  committee,
                  posts: nextPosts,
                  mediaLinks: nextMedia,
                  forms,
                });
              }, 'تمت إضافة رابط الوسائط بنجاح.')
            }
            onUpdate={(id, payload) =>
              runMutation(async () => {
                const updated = await apiClient.updateMediaLink(id, payload);
                const nextMedia = upsertMediaLinkList(mediaLinks, updated);
                const nextPosts = syncMediaLinksIntoPosts(posts, nextMedia);
                setMediaLinks(nextMedia);
                setPosts(nextPosts);
                notifyParent({
                  committee,
                  posts: nextPosts,
                  mediaLinks: nextMedia,
                  forms,
                });
              }, 'تم تحديث رابط الوسائط بنجاح.')
            }
            onDelete={(id) =>
              runMutation(async () => {
                await apiClient.deleteMediaLink(id);
                const nextMedia = removeById(mediaLinks, id);
                const nextPosts = syncMediaLinksIntoPosts(posts, nextMedia);
                setMediaLinks(nextMedia);
                setPosts(nextPosts);
                notifyParent({
                  committee,
                  posts: nextPosts,
                  mediaLinks: nextMedia,
                  forms,
                });
              }, 'تم حذف رابط الوسائط بنجاح.')
            }
          />
        )}

        {activeSection === 'forms' && (
          <FormsAdminPanel
            forms={forms}
            isBusy={isBusy}
            initialEditingItem={initialEditingItem}
            onCreate={(payload) =>
              runMutation(async () => {
                const created = await apiClient.createForm(payload);
                const nextForms = upsertFormList(forms, created);
                setForms(nextForms);
                notifyParent({ committee, posts, mediaLinks, forms: nextForms });
              }, 'تمت إضافة نموذج Google Forms بنجاح.')
            }
            onUpdate={(id, payload) =>
              runMutation(async () => {
                const updated = await apiClient.updateForm(id, payload);
                const nextForms = upsertFormList(forms, updated);
                setForms(nextForms);
                notifyParent({ committee, posts, mediaLinks, forms: nextForms });
              }, 'تم تحديث نموذج Google Forms بنجاح.')
            }
            onDelete={(id) =>
              runMutation(async () => {
                await apiClient.deleteForm(id);
                const nextForms = removeById(forms, id);
                setForms(nextForms);
                notifyParent({ committee, posts, mediaLinks, forms: nextForms });
              }, 'تم حذف نموذج Google Forms بنجاح.')
            }
          />
        )}
      </div>
    </section>
  );
}
