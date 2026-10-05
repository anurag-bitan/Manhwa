export function buildPanelCards(storyData, fallbackUrls = []) {
  const urls = storyData?.image_urls || fallbackUrls || [];
  const segments = storyData?.final_video_segments;
  if (Array.isArray(segments) && segments.length > 0) {
    return segments.map((seg, idx) => {
      const pageIndex = Number.isFinite(Number(seg.image_page_index))
        ? Number(seg.image_page_index)
        : 0;
      return {
        id: seg.segment_id || `panel-${idx}`,
        src: urls[pageIndex] || urls[0] || "",
        bbox: Array.isArray(seg.panel_bbox) ? seg.panel_bbox : null,
        label: `Panel ${idx + 1}`,
      };
    });
  }
  return urls.map((src, idx) => ({
    id: `page-${idx}`,
    src,
    bbox: null,
    label: `Panel ${idx + 1}`,
  }));
}
