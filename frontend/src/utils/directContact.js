/**
 * Build a wa.me chat URL from a local (Israeli) or international phone number.
 * Returns '' when the number is unusable.
 */
export function buildWhatsAppChatUrl(phone) {
  const raw = typeof phone === 'string' ? phone.trim() : '';
  if (!raw) return '';
  let digits = raw.replace(/[^\d+]/g, '');
  if (digits.startsWith('+')) digits = digits.slice(1);
  else if (digits.startsWith('00')) digits = digits.slice(2);
  else if (digits.startsWith('0')) digits = `972${digits.slice(1)}`;
  if (digits.length < 8 || digits.length > 15) return '';
  return `https://wa.me/${digits}`;
}
