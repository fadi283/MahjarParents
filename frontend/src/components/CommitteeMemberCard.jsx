import React from 'react';
import { API_BASE_URL, resolveMediaUrl } from '../utils/apiConfig.js';

export default function CommitteeMemberCard({ member, apiBaseUrl = API_BASE_URL }) {
  if (!member) return null;

  const fullName = member.fullName ?? member.full_name ?? '';
  const role = member.role ?? member.title ?? '';
  const responsibilitySummary =
    member.responsibilitySummary ?? member.responsibility_summary ?? '';
  const avatarUrl = member.avatarUrl ?? member.avatar_url ?? '';

  const hasAvatar = Boolean(avatarUrl && avatarUrl.trim());
  const resolvedAvatarUrl = hasAvatar
    ? resolveMediaUrl(avatarUrl.trim(), apiBaseUrl)
    : '';

  return (
    <article
      dir="rtl"
      className="committee-card"
      aria-label={`${fullName} - ${role}`}
    >
      <div className="committee-card__header">
        {hasAvatar && (
          <div className="committee-card__avatar-wrapper">
            <img
              src={resolvedAvatarUrl}
              alt={`صورة ${fullName} - ${role}`}
              loading="lazy"
              className="committee-card__avatar"
              width="64"
              height="64"
            />
          </div>
        )}

        <div className="committee-card__identity">
          <h3 className="committee-card__name">{fullName}</h3>
          <span className="committee-card__role">{role}</span>
        </div>
      </div>

      <p className="committee-card__summary">{responsibilitySummary}</p>
    </article>
  );
}
