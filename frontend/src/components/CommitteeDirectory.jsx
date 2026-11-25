import React from 'react';
import CommitteeMemberCard from './CommitteeMemberCard.jsx';

export default function CommitteeDirectory({ members = [] }) {
  return (
    <section
      dir="rtl"
      className="committee-directory"
      aria-labelledby="committee-directory-heading"
    >
      <div className="committee-directory__header">
        <h2 id="committee-directory-heading" className="committee-directory__title">
          أعضاء لجنة أولياء الأمور
        </h2>
        <p className="committee-directory__subtitle">
          تعرف على ممثلي أهالي الطلاب وأدوارهم في دعم المسيرة التعليمية والتربوية في مدرسة المحجر الابتدائية.
        </p>
      </div>

      {members.length === 0 ? (
        <div className="committee-directory__empty" role="status">
          <p>لا يوجد أعضاء مسجلون حالياً في دليل اللجنة.</p>
        </div>
      ) : (
        <div className="committee-directory__grid" role="list">
          {members.map((member, index) => (
            <div
              key={member.id ?? `${member.fullName}-${index}`}
              className="committee-directory__item"
              role="listitem"
            >
              <CommitteeMemberCard member={member} />
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
