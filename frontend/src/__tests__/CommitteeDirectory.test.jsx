import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import CommitteeMemberCard from '../components/CommitteeMemberCard.jsx';
import CommitteeDirectory from '../components/CommitteeDirectory.jsx';
import App from '../App.jsx';

const sampleMemberWithAvatarAndEmail = {
  id: 1,
  fullName: 'أحمد محمود العلي',
  role: 'رئيس اللجنة',
  responsibilitySummary: 'الإشراف العام على أعمال اللجنة والتنسيق المباشر مع إدارة المدرسة لمتابعة شؤون الطلاب.',
  avatarUrl: 'https://example.com/avatars/ahmad.webp',
  email: 'ahmad@mahjar-parents.org',
};

const sampleMemberWithoutAvatarOrEmail = {
  id: 2,
  fullName: 'فاطمة خالد الحسن',
  role: 'أمين الصندوق',
  responsibilitySummary: 'إدارة الموارد المالية للأنشطة المدرسية وتوثيق المساهمات المجتمعية بشفافية.',
};

test('CommitteeMemberCard renders full name, role/title, and brief responsibility summary inside an RTL-compliant card', () => {
  const html = renderToStaticMarkup(
    <CommitteeMemberCard member={sampleMemberWithAvatarAndEmail} />
  );

  assert.match(html, /dir="rtl"/, 'Card should explicitly support RTL direction');
  assert.ok(html.includes('أحمد محمود العلي'), 'Card should display full name');
  assert.ok(html.includes('رئيس اللجنة'), 'Card should display role/title');
  assert.ok(
    html.includes('الإشراف العام على أعمال اللجنة والتنسيق المباشر مع إدارة المدرسة لمتابعة شؤون الطلاب.'),
    'Card should display brief responsibility summary'
  );
});

test('CommitteeMemberCard renders optional avatar image with lazy loading when avatarUrl is provided', () => {
  const html = renderToStaticMarkup(
    <CommitteeMemberCard member={sampleMemberWithAvatarAndEmail} />
  );

  assert.match(html, /<img[^>]+src="https:\/\/example\.com\/avatars\/ahmad\.webp"/, 'Avatar image src should be rendered');
  assert.match(html, /<img[^>]+alt="[^"]*أحمد محمود العلي[^"]*"/, 'Avatar image should have accessible alt text containing member name');
  assert.match(html, /<img[^>]+loading="lazy"/, 'Avatar image should use loading="lazy" per NFR performance requirements');
});

test('CommitteeMemberCard does NOT render an initials circle or avatar placeholder when avatarUrl is omitted or empty', () => {
  const html = renderToStaticMarkup(
    <CommitteeMemberCard member={sampleMemberWithoutAvatarOrEmail} />
  );

  assert.doesNotMatch(html, /<img/, 'Should not render an <img> tag when avatarUrl is omitted');
  assert.doesNotMatch(html, /avatar-placeholder/, 'Should NOT render any initials circle / avatar placeholder');
  assert.ok(html.includes('فاطمة خالد الحسن'), 'Should still render member full name');
  assert.ok(html.includes('أمين الصندوق'), 'Should still render member role');
});

test('CommitteeMemberCard does NOT render a "للتواصل" button or mailto link even when member has an email or contactUrl', () => {
  const html = renderToStaticMarkup(
    <CommitteeMemberCard member={sampleMemberWithAvatarAndEmail} />
  );

  assert.doesNotMatch(html, /mailto:/, 'Should NOT render any mailto: contact link');
  assert.doesNotMatch(html, /للتواصل/, 'Should NOT render "للتواصل" contact button');
  assert.doesNotMatch(html, /committee-card__actions/, 'Should NOT render committee-card__actions container');
  assert.doesNotMatch(html, /<a\b/, 'Should NOT render any <a> action link');
  assert.doesNotMatch(html, /<button/, 'Should NOT render any <button> element');

  const contactUrlHtml = renderToStaticMarkup(
    <CommitteeMemberCard
      member={{
        ...sampleMemberWithoutAvatarOrEmail,
        contactUrl: 'mailto:contact@mahjar-parents.org',
        contact_url: 'https://example.com/contact',
      }}
    />
  );
  assert.doesNotMatch(contactUrlHtml, /mailto:/, 'Should NOT render mailto: from contactUrl');
  assert.doesNotMatch(contactUrlHtml, /للتواصل/, 'Should NOT render "للتواصل" from contactUrl');
  assert.doesNotMatch(contactUrlHtml, /committee-card__actions/, 'Should NOT render actions container');
  assert.doesNotMatch(contactUrlHtml, /<a\b/, 'Should NOT render any <a> action link');
});

test('CommitteeMemberCard does NOT render any button ("للتواصل" or "تفاصيل المهام") when member has no email', () => {
  const html = renderToStaticMarkup(
    <CommitteeMemberCard member={sampleMemberWithoutAvatarOrEmail} />
  );

  assert.doesNotMatch(html, /تفاصيل المهام/, 'Should NOT render "تفاصيل المهام" button');
  assert.doesNotMatch(html, /للتواصل/, 'Should NOT render "للتواصل" button when no email is provided');
  assert.doesNotMatch(html, /<button/, 'Should NOT render any <button> element');
  assert.doesNotMatch(html, /<a\b/, 'Should NOT render any <a> action link');
});

test('CommitteeDirectory renders a mobile-first RTL section with all provided committee members and no filter buttons', () => {
  const members = [sampleMemberWithAvatarAndEmail, sampleMemberWithoutAvatarOrEmail];
  const html = renderToStaticMarkup(<CommitteeDirectory members={members} />);

  assert.match(html, /dir="rtl"/, 'CommitteeDirectory section must be RTL');
  assert.ok(html.includes('أعضاء لجنة أولياء الأمور'), 'Should render Arabic section heading for committee directory');
  assert.ok(html.includes('أحمد محمود العلي'), 'Should render first member');
  assert.ok(html.includes('فاطمة خالد الحسن'), 'Should render second member');
  assert.doesNotMatch(html, /role="toolbar"/, 'CommitteeDirectory must NOT render any filter toolbar');
});

test('CommitteeDirectory handles empty state gracefully when members array is empty', () => {
  const html = renderToStaticMarkup(<CommitteeDirectory members={[]} />);

  assert.match(html, /dir="rtl"/, 'Empty state must remain RTL');
  assert.ok(
    html.includes('لا يوجد أعضاء مسجلون حالياً'),
    'Should display an Arabic empty state message when no members exist'
  );
});

test('App renders the CommitteeDirectory with default committee members in RTL layout', () => {
  const html = renderToStaticMarkup(<App initialPage="committee" />);

  assert.match(html, /dir="rtl"/, 'App root must enforce RTL');
  assert.ok(html.includes('لجنة أولياء أمور الطلاب'), 'App header should be rendered');
  assert.match(html, /<img[^>]+src="\/logo\.jpg"/, 'App header should display the school committee logo');
  assert.match(html, /<img[^>]+alt="[^"]*شعار لجنة أولياء أمور مدرسة المحجر الابتدائية[^"]*"/, 'Logo should have accessible Arabic alt text');
  assert.ok(
    html.indexOf('app-header__text') < html.indexOf('app-header__logo'),
    'In RTL header, text block should come first (right side) and logo second (left side)'
  );
  assert.ok(html.includes('أعضاء لجنة أولياء الأمور'), 'App should render the CommitteeDirectory section');
  assert.ok(html.includes('فادي وليد اغبارية'), 'App should render committee chair فادي وليد اغبارية');
  assert.ok(
    html.includes('قيادة اللجنة وتمثيل الأهالي أمام الجهات الرسمية، والإشراف العام على المشاريع التربوية.'),
    'App should render updated job description for committee chair'
  );
  assert.ok(html.includes('محمد شاكر إغبارية'), 'App should render vice chair محمد شاكر إغبارية');
  assert.ok(
    html.includes('مساندة الرئيس والنيابة عنه، والإشراف على مشروع العريشة وتنظيم حركة السير عند انتهاء الدوام.'),
    'App should render updated job description for vice chair'
  );
  assert.ok(html.includes('طه علي اغباريه'), 'App should render treasurer طه علي اغباريه');
  assert.ok(
    html.includes('إدارة الشؤون المالية والميزانيات بشفافية، واستقبال توجهات ومقترحات الأهالي هاتفياً وإيصالها للجنة.'),
    'App should render updated job description for treasurer'
  );
  assert.ok(html.includes('حسن البنا محمد جبارين'), 'App should render member حسن البنا محمد جبارين');
  assert.ok(
    html.includes('تخطيط وتنسيق الفعاليات اللامنهجية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.'),
    'App should render updated job description for committee members'
  );
  assert.ok(
    html.includes('تمثيل الأهالي أمام اللجنة المحلية، وطرح المبادرات التربوية، والتواصل مع الأهالي لنقل احتياجات الطلاب.'),
    'App should render updated job description for حجازي محمد اغبارية'
  );
  assert.doesNotMatch(html, /avatar-placeholder/, 'App should not render any initials circle');
  assert.doesNotMatch(html, /تفاصيل المهام/, 'App should not render "تفاصيل المهام" button');
  assert.doesNotMatch(html, />للتواصل</, 'App committee directory should NOT render "للتواصل" button');
  assert.doesNotMatch(html, /committee-card__actions/, 'App committee directory should NOT render committee-card__actions');
  assert.doesNotMatch(html, /mailto:/, 'App committee directory should NOT render any mailto: links');
});

test('CommitteeMemberCard supports snake_case fields from Flask API payloads, hides avatar when whitespace, and omits email contact actions', () => {
  const apiMember = {
    id: 99,
    full_name: 'ليلى عبد الرحمن',
    role: 'عضو لجنة',
    responsibility_summary: 'متابعة الأنشطة الثقافية والمكتبة المدرسية.',
    avatar_url: '   ',
    email: 'laila@mahjar-parents.org',
  };

  const html = renderToStaticMarkup(<CommitteeMemberCard member={apiMember} />);

  assert.ok(html.includes('ليلى عبد الرحمن'), 'Should support full_name snake_case field');
  assert.ok(html.includes('عضو لجنة'), 'Should render role');
  assert.ok(html.includes('متابعة الأنشطة الثقافية والمكتبة المدرسية.'), 'Should support responsibility_summary snake_case field');
  assert.doesNotMatch(html, /<img/, 'Whitespace-only avatar_url should not render an <img>');
  assert.doesNotMatch(html, /avatar-placeholder/, 'Whitespace-only avatar_url should not render any placeholder circle');
  assert.doesNotMatch(html, /mailto:/, 'Should NOT render mailto: link for email');
  assert.doesNotMatch(html, /للتواصل/, 'Should NOT render "للتواصل" label');
});
