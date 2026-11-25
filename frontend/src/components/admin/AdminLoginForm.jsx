import React, { useState } from 'react';
import { TOUCH_TARGET_STYLE } from './adminShared.jsx';

export default function AdminLoginForm({
  onLogin,
  onCancel,
  isLoading = false,
  error = '',
}) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState('');

  const activeError = localError || error;

  const handleSubmit = async (event) => {
    event.preventDefault();
    const trimmedUser = username.trim();
    if (!trimmedUser || !password) {
      setLocalError('يرجى إدخال اسم المستخدم وكلمة المرور.');
      return;
    }
    setLocalError('');
    if (typeof onLogin === 'function') {
      await onLogin(trimmedUser, password);
    }
  };

  return (
    <section
      dir="rtl"
      className="admin-login"
      aria-labelledby="admin-login-heading"
    >
      <div className="admin-login__card">
        <span className="admin-login__badge">منطقة محمية لمسؤولي اللجنة</span>
        <h2 id="admin-login-heading" className="admin-login__title">
          تسجيل الدخول إلى لوحة الإدارة
        </h2>
        <p className="admin-login__subtitle">
          أدخل بيانات الاعتماد الإدارية لإدارة أعضاء اللجنة، الإعلانات، روابط الوسائط، ونماذج Google Forms.
        </p>

        {activeError && (
          <div className="admin-alert admin-alert--error" role="alert">
            {activeError}
          </div>
        )}

        <form className="admin-login__form" onSubmit={handleSubmit} noValidate>
          <div className="admin-field">
            <label htmlFor="admin-username" className="admin-field__label">
              اسم المستخدم
            </label>
            <input
              id="admin-username"
              name="username"
              type="text"
              autoComplete="username"
              className="admin-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          <div className="admin-field">
            <label htmlFor="admin-password" className="admin-field__label">
              كلمة المرور
            </label>
            <input
              id="admin-password"
              name="password"
              type="password"
              autoComplete="current-password"
              className="admin-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={isLoading}
              required
            />
          </div>

          <div className="admin-login__actions">
            <button
              type="submit"
              className="admin-btn admin-btn--primary"
              style={TOUCH_TARGET_STYLE}
              disabled={isLoading}
            >
              {isLoading ? 'جارٍ التحقق...' : 'تسجيل الدخول'}
            </button>

            {typeof onCancel === 'function' && (
              <button
                type="button"
                className="admin-btn admin-btn--secondary"
                style={TOUCH_TARGET_STYLE}
                disabled={isLoading}
                onClick={onCancel}
              >
                العودة إلى المنصة
              </button>
            )}
          </div>
        </form>
      </div>
    </section>
  );
}
