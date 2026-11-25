import React, { useCallback, useEffect, useRef, useState } from 'react';
import { adminApi, translateAdminError } from '../../utils/adminApi.js';
import {
  removeById,
  upsertCommitteeList,
  upsertFormList,
  upsertPostList,
} from '../../utils/adminState.js';
import AdminLoginForm from './AdminLoginForm.jsx';
import CommitteeAdminPanel from './CommitteeAdminPanel.jsx';
import PostsAdminPanel from './PostsAdminPanel.jsx';
import FormsAdminPanel from './FormsAdminPanel.jsx';
import { TOUCH_TARGET_STYLE } from './adminShared.jsx';

export const ADMIN_SECTIONS = [
  { id: 'committee', label: 'أعضاء اللجنة' },
  { id: 'posts', label: 'الإعلانات والفعاليات' },
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
  const [activeSection, setActiveSection] = useState(() => {
    if (ADMIN_SECTIONS.some((section) => section.id === initialSection)) {
      return initialSection;
    }
    return initialSection === 'media' ? 'posts' : 'committee';
  });
  const [committee, setCommittee] = useState(() => initialData?.committee ?? []);
  const [posts, setPosts] = useState(() => initialData?.posts ?? []);
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
    const [committeeRes, postsRes, formsRes] = await Promise.all([
      apiClient.listCommittee(),
      apiClient.listPosts(),
      apiClient.listForms(),
    ]);
    const nextCommittee = Array.isArray(committeeRes) ? committeeRes : [];
    const nextPosts = Array.isArray(postsRes) ? postsRes : [];
    const nextForms = Array.isArray(formsRes) ? formsRes : [];

    setCommittee(nextCommittee);
    setPosts(nextPosts);
    setForms(nextForms);
    notifyParent({
      committee: nextCommittee,
      posts: nextPosts,
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
                notifyParent({ committee: nextCommittee, posts, forms });
              }, 'تمت إضافة عضو اللجنة بنجاح.')
            }
            onUpdate={(id, payload) =>
              runMutation(async () => {
                const updated = await apiClient.updateCommitteeMember(id, payload);
                const nextCommittee = upsertCommitteeList(committee, updated);
                setCommittee(nextCommittee);
                notifyParent({ committee: nextCommittee, posts, forms });
              }, 'تم تحديث بيانات عضو اللجنة بنجاح.')
            }
            onDelete={(id) =>
              runMutation(async () => {
                await apiClient.deleteCommitteeMember(id);
                const nextCommittee = removeById(committee, id);
                setCommittee(nextCommittee);
                notifyParent({ committee: nextCommittee, posts, forms });
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
                const nextPosts = upsertPostList(posts, created);
                setPosts(nextPosts);
                notifyParent({ committee, posts: nextPosts, forms });
              }, 'تم نشر الإعلان بنجاح.')
            }
            onUpdate={(id, payload) =>
              runMutation(async () => {
                const updated = await apiClient.updatePost(id, payload);
                const nextPosts = upsertPostList(posts, updated);
                setPosts(nextPosts);
                notifyParent({ committee, posts: nextPosts, forms });
              }, 'تم تحديث الإعلان بنجاح.')
            }
            onDelete={(id) =>
              runMutation(async () => {
                await apiClient.deletePost(id);
                const nextPosts = removeById(posts, id);
                setPosts(nextPosts);
                notifyParent({ committee, posts: nextPosts, forms });
              }, 'تم حذف الإعلان بنجاح.')
            }
            onReorder={(orderedIds) =>
              runMutation(async () => {
                const reordered = await apiClient.reorderPosts(orderedIds);
                const nextPosts = Array.isArray(reordered) ? reordered : posts;
                setPosts(nextPosts);
                notifyParent({ committee, posts: nextPosts, forms });
              }, 'تم تحديث ترتيب الإعلانات بنجاح.')
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
                notifyParent({ committee, posts, forms: nextForms });
              }, 'تمت إضافة نموذج Google Forms بنجاح.')
            }
            onUpdate={(id, payload) =>
              runMutation(async () => {
                const updated = await apiClient.updateForm(id, payload);
                const nextForms = upsertFormList(forms, updated);
                setForms(nextForms);
                notifyParent({ committee, posts, forms: nextForms });
              }, 'تم تحديث نموذج Google Forms بنجاح.')
            }
            onDelete={(id) =>
              runMutation(async () => {
                await apiClient.deleteForm(id);
                const nextForms = removeById(forms, id);
                setForms(nextForms);
                notifyParent({ committee, posts, forms: nextForms });
              }, 'تم حذف نموذج Google Forms بنجاح.')
            }
          />
        )}
      </div>
    </section>
  );
}
