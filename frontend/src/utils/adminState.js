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

function parseDisplayOrder(item) {
  const raw = item?.displayOrder ?? item?.display_order;
  if (raw === null || raw === undefined || raw === '' || typeof raw === 'boolean') {
    return null;
  }
  const parsed = Number(raw);
  return Number.isInteger(parsed) && parsed >= 1 ? parsed : null;
}

export function upsertPostList(list = [], post) {
  return upsertItem(list, post).sort((a, b) => {
    const orderA = parseDisplayOrder(a);
    const orderB = parseDisplayOrder(b);
    if (orderA !== null || orderB !== null) {
      if (orderA === null) return 1;
      if (orderB === null) return -1;
      if (orderA !== orderB) {
        return orderA - orderB;
      }
    }
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

export function moveItemInList(list = [], itemId, direction) {
  if (!Array.isArray(list) || list.length === 0) {
    return { moved: false, nextItems: [], orderedIds: [] };
  }
  const index = list.findIndex((item) => String(item.id) === String(itemId));
  if (index === -1) {
    return {
      moved: false,
      nextItems: [...list],
      orderedIds: list.map((item) => item.id),
    };
  }
  const targetIndex =
    direction === 'up' ? index - 1 : direction === 'down' ? index + 1 : -1;
  if (targetIndex < 0 || targetIndex >= list.length) {
    return {
      moved: false,
      nextItems: [...list],
      orderedIds: list.map((item) => item.id),
    };
  }
  const swapped = [...list];
  [swapped[index], swapped[targetIndex]] = [swapped[targetIndex], swapped[index]];
  const nextItems = swapped.map((item, idx) => ({
    ...item,
    displayOrder: idx + 1,
    display_order: idx + 1,
  }));
  return {
    moved: true,
    nextItems,
    orderedIds: nextItems.map((item) => item.id),
  };
}

export function reorderItemsByDrag(list = [], draggedId, targetId) {
  if (!Array.isArray(list) || list.length < 2) {
    const safeList = Array.isArray(list) ? [...list] : [];
    return {
      moved: false,
      nextItems: safeList,
      orderedIds: safeList.map((item) => item.id),
    };
  }
  const fromIndex = list.findIndex((item) => String(item.id) === String(draggedId));
  const toIndex = list.findIndex((item) => String(item.id) === String(targetId));
  if (fromIndex === -1 || toIndex === -1 || fromIndex === toIndex) {
    return {
      moved: false,
      nextItems: [...list],
      orderedIds: list.map((item) => item.id),
    };
  }
  const reordered = [...list];
  const [movedItem] = reordered.splice(fromIndex, 1);
  reordered.splice(toIndex, 0, movedItem);
  const nextItems = reordered.map((item, idx) => ({
    ...item,
    displayOrder: idx + 1,
    display_order: idx + 1,
  }));
  return {
    moved: true,
    nextItems,
    orderedIds: nextItems.map((item) => item.id),
  };
}

export function movePostInList(list = [], postId, direction) {
  const { moved, nextItems, orderedIds } = moveItemInList(list, postId, direction);
  return { moved, nextPosts: nextItems, orderedIds };
}

export function reorderPostsByDrag(list = [], draggedId, targetId) {
  const { moved, nextItems, orderedIds } = reorderItemsByDrag(list, draggedId, targetId);
  return { moved, nextPosts: nextItems, orderedIds };
}

export function upsertMediaLinkList(list = [], mediaLink) {
  return upsertItem(list, mediaLink);
}

export function upsertFormList(list = [], form) {
  if (!form) return [...list];
  const exists = list.some((entry) => String(entry.id) === String(form.id));
  const shouldShiftExisting =
    !exists &&
    parseDisplayOrder(form) === 1 &&
    list.some((entry) => parseDisplayOrder(entry) === 1);
  const baseList = shouldShiftExisting
    ? list.map((entry) => {
        const order = parseDisplayOrder(entry);
        if (order === null) return entry;
        return {
          ...entry,
          displayOrder: order + 1,
          display_order: order + 1,
        };
      })
    : list;

  return upsertItem(baseList, form).sort((a, b) => {
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
