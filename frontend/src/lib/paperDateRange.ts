import type { PaperDateRangeValue } from "@/components/PaperDateFilter";

export const readPaperDateRange = (params: URLSearchParams): PaperDateRangeValue => ({
  startDate: params.get("start_date") || undefined,
  endDate: params.get("end_date") || undefined,
});

export const withPaperDateRange = (
  current: URLSearchParams,
  value: PaperDateRangeValue,
) => {
  const next = new URLSearchParams(current);
  if (value.startDate) next.set("start_date", value.startDate);
  else next.delete("start_date");
  if (value.endDate) next.set("end_date", value.endDate);
  else next.delete("end_date");
  next.delete("time");
  return next;
};
