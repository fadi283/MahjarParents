function upsertItem(list = [], item) {
  if (!item) return [...list];
  const exists = list.some((entry) => String(entry.id) === String(item.id));
  if (exists) {
    return list.map((entry) => (String(entry.id) === String(item.id) ? item : entry));
  }
  return [item, ...list];
}

export function upsertCommitteeList(list = [], member) {
  return upsertItem(list, member).sort((a, b) => {
    const orderA = a?.displayOrder ?? a?.display_order ?? 9999;
    const orderB = b?.displayOrder ?? b?.display_order ?? 9999;
    if (orderA !== orderB) {
      return Number(orderA) - Number(orderB);
    }
    return (Number(a?.id) || 0) - (Number(b?.id) || 0);
  });
}

export function upsertPostList(list = [], post) {
  return upsertItem(list, post).sort((a, b) => {
    const rawA = a?.publishedAt ?? a?.published_at ?? '';
    const rawB = b?.publishedAt ?? b?.published_at ?? '';
    const timeA = rawA ? new Date(rawA).getTime() : 0;
    const timeB = rawB ? new Date(rawB).getTime() : 0;
    const validA = Number.isNaN(timeA) ? 0 : timeA;
    const validB = Number.isNaN(timeB) ? 0 : timeB;
    if (validB !== validA) {
      return validB - validA;
    }
    return (Number(b?.id) || 0) - (Number(a?.id) || 0);
  });
}

export function upsertMediaLinkList(list = [], mediaLink) {
  return upsertItem(list, mediaLink);
}

export function upsertFormList(list = [], form) {
  return upsertItem(list, form).sort((a, b) => {
    const orderA = a?.displayOrder ?? a?.display_order ?? 9999;
    const orderB = b?.displayOrder ?? b?.display_order ?? 9999;
    if (orderA !== orderB) {
      return Number(orderA) - Number(orderB);
    }
    return (Number(a?.id) || 0) - (Number(b?.id) || 0);
  });
}

export function removeById(list = [], id) {
  return list.filter((item) => String(item.id) !== String(id));
}

export function syncMediaLinksIntoPosts(posts = [], mediaLinks = []) {
  return posts.map((post) => ({
    ...post,
    mediaLinks: mediaLinks.filter(
      (link) => link?.postId !== null && link?.postId !== undefined && String(link.postId) === String(post.id)
    ),
  }));
}
