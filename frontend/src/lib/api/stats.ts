import type { ApiRequest } from "../apiTransport";

import { apiRequest } from "./request";

export interface TrendPoint {
  month: string;
  percent: number;
}

export interface TrendsResponse {
  code_availability: TrendPoint[];
  hf_artifacts: TrendPoint[];
}


export class StatsApi {
  constructor(private readonly request: ApiRequest) {}

  trends(): Promise<TrendsResponse> {
    return this.request("/stats/trends");
  }
}

export const statsApi = new StatsApi(apiRequest);
