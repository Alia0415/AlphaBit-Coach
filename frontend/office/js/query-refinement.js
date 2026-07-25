const TIME_RANGE_PATTERN =
  /(?:近|过去|最近)\s*(?:[一二三四五六七八九十\d]+\s*)?(?:个\s*)?(?:月|年)|近期|最近一段时间/;

export function applyClarificationOption(query, option, type) {
  const normalizedQuery = String(query || "").trim();
  const normalizedOption = String(option || "").trim();
  if (!normalizedOption) return normalizedQuery;
  if (type !== "time_range") return normalizedQuery;

  if (TIME_RANGE_PATTERN.test(normalizedQuery)) {
    return normalizedQuery.replace(TIME_RANGE_PATTERN, normalizedOption);
  }
  const punctuation = /[。！？!?]$/.test(normalizedQuery) ? "" : "；";
  return `${normalizedQuery}${punctuation}时间范围为${normalizedOption}`;
}

export function buildQueryContext(originalQuery, rewrittenQuery, finalQuery) {
  const final = String(finalQuery || "").trim();
  const original = String(originalQuery || final).trim();
  const rewritten = String(rewrittenQuery || final).trim();
  return {
    originalQuery: original,
    rewrittenQuery: rewritten,
    finalQuery: final,
  };
}
